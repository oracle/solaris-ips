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
# Copyright (c) 2011, 2016, Oracle and/or its affiliates. All rights reserved.
#

import atexit
import collections
import errno
import tarfile as tf
import os
import shutil
import six
import sys
import tempfile
from six.moves.urllib.parse import unquote

import pkg
import pkg.client.api_errors as apx
import pkg.client.publisher
import pkg.digest as digest
import pkg.fmri
import pkg.manifest
import pkg.misc
import pkg.portable
import pkg.p5i
import pkg.pkggzip
import pkg.pkgtarfile as ptf
from pkg.misc import force_bytes, force_str

if sys.version > '3':
        long = int

class ArchiveErrors(apx.ApiException):
        """Base exception class for archive class errors."""


class InvalidArchiveIndex(ArchiveErrors):
        """Used to indicate that the specified index is in a format not
        supported or recognized by this version of the pkg(5) ArchiveIndex
        class."""

        def __init__(self, arc_name):
                ArchiveErrors.__init__(self)
                self.__name = arc_name

        def __str__(self):
                return _("{0} is not in a supported or recognizable archive "
                    "index format.").format(self.__name)


class ArchiveIndex(object):
        """Class representing a pkg(5) archive table of contents and a set of
        interfaces to populate and retrieve entries.

        Entries in this file are written in the following format:

            <name>NUL<offset>NUL<entry_size>NUL<size>NUL<typeflag>NULNL

            <name> is a string containing the pathname of the file in the
            archive.  It can be up to 65,535 bytes in length.

            <offset> is an unsigned long long integer containing the relative
            offset in bytes of the first header block for the file in the
            archive.  The offset is relative to the end of the last block of
            the first file in the archive.

            <entry_size> is an unsigned long long integer containing the size of
            the file's entry in bytes in the archive (including archive
            headers and trailers for the entry).

            <size> is an unsigned long long integer containing the size of the
            file in bytes in the archive.

            <typeflag> is a single character representing the type of the file
            in the archive.  Possible values are:
                0 Regular File
                1 Hard Link
                2 Symbolic Link
                5 Directory or subdirectory"""

        version = None
        CURRENT_VERSION = 0
        COMPATIBLE_VERSIONS = 0,
        ENTRY_FORMAT = "{0}\0{1:d}\0{2:d}\0{3:d}\0{4}\0\n"

        def __init__(self, name, mode="r", version=None):
                """Open a pkg(5) archive table of contents file.

                'name' should be the absolute path of the file to use when
                reading or writing index data.

                'mode' indicates whether the index is being used for reading
                or writing, and can be 'r' or 'w'.  Appending to or updating
                a table of contents file is not supported.

                'version' is an optional integer value specifying the version
                of the index to be read or written.  If not specified, the
                current version is assumed.
                """

                assert os.path.isabs(name)
                if version is None:
                        version = self.CURRENT_VERSION
                if version not in self.COMPATIBLE_VERSIONS:
                        raise InvalidArchiveIndex(name)

                self.__closed = False
                self.__name = name
                self.__mode = mode
                try:
                        self.__file = pkg.pkggzip.PkgGzipFile(self.__name,
                            self.__mode)
                except IOError as e:
                        if e.errno:
                                raise
                        # Underlying gzip library raises this exception if the
                        # file isn't a valid gzip file.  So, assume that if
                        # errno isn't set, this is a gzip error instead.
                        raise InvalidArchiveIndex(name)

                self.version = version

        def __exit__(self, exc_type, exc_value, exc_tb):
                """Context handler that ensures archive is automatically closed
                in a non-error condition scenario.  This enables 'with' usage.
                """
                if exc_type or exc_value or exc_tb:
                        # Only close filehandles in an error condition.
                        self.__close_fh()
                else:
                        # Close archive normally in all other cases.
                        self.close()

        @property
        def pathname(self):
                """The absolute path of the archive index file."""
                return self.__name

        def add(self, name, offset, entry_size, size, typeflag):
                """Add an entry for the given archive file to the table of
                contents."""

                # GzipFile.write requires bytes input
                self.__file.write(force_bytes(self.ENTRY_FORMAT.format(
                    name, offset, entry_size, size, typeflag)))

        def offsets(self):
                """Returns a generator that yields tuples of the form (name,
                offset) for each file in the index."""

                self.__file.seek(0)
                l = None
                try:
                        for line in self.__file:
                                # Under Python 3, indexing on a bytes will
                                # return an integer representing the
                                # unicode code point of that character; we
                                # need to use slicing to get the character.
                                if line[-2:-1] != b"\0":
                                        # Filename contained newline.
                                        if l is None:
                                                l = line
                                        else:
                                                l += b"\n"
                                                l += line
                                        continue
                                elif l is None:
                                        l = line

                                name, offset, ignored = l.split(b"\0", 2)
                                yield force_str(name), long(offset)
                                l = None
                except ValueError:
                        raise InvalidArchiveIndex(self.__name)
                except IOError as e:
                        if e.errno:
                                raise
                        # Underlying gzip library raises this exception if the
                        # file isn't a valid gzip file.  So, assume that if
                        # errno isn't set, this is a gzip error instead.
                        raise InvalidArchiveIndex(self.__name)

        def close(self):
                """Close the index.  No further operations can be performed
                using this object once closed."""

                if self.__closed:
                        return
                if self.__file:
                        self.__file.close()
                        self.__file = None
                self.__closed = True


class InvalidArchive(ArchiveErrors):
        """Used to indicate that the specified archive is in a format not
        supported or recognized by this version of the pkg(5) Archive class.
        """

        def __init__(self, arc_name):
                ArchiveErrors.__init__(self)
                self.arc_name = arc_name

        def __str__(self):
                return _("Archive {0} is missing, unsupported, or corrupt.").format(
                    self.arc_name)


class CorruptArchiveFiles(ArchiveErrors):
        """Used to indicate that the specified file(s) could not be found in the
        archive.
        """

        def __init__(self, arc_name, files):
                ArchiveErrors.__init__(self)
                self.arc_name = arc_name
                self.files = files

        def __str__(self):
                return _("Package archive {arc_name} contains corrupt "
                    "entries for the requested package file(s):\n{files}.").format(
                    arc_name=self.arc_name,
                    files="\n".join(self.files))


class UnknownArchiveFiles(ArchiveErrors):
        """Used to indicate that the specified file(s) could not be found in the
        archive.
        """

        def __init__(self, arc_name, files):
                ArchiveErrors.__init__(self)
                self.arc_name = arc_name
                self.files = files

        def __str__(self):
                return _("Package archive {arc_name} does not contain the "
                    "requested package file(s):\n{files}.").format(
                    arc_name=self.arc_name,
                    files="\n".join(self.files))


class UnknownPackageManifest(ArchiveErrors):
        """Used to indicate that a manifest for the specified package could not
        be found in the archive.
        """

        def __init__(self, arc_name, pfmri):
                ArchiveErrors.__init__(self)
                self.arc_name = arc_name
                self.pfmri = pfmri

        def __str__(self):
                return _("No package manifest for package '{pfmri}' exists "
                    "in archive {arc_name}.").format(**self.__dict__)


class Archive(object):
        """Class representing a pkg(5) archive and a set of interfaces to
        populate it and retrieve data from it.

        This class stores package data in pax archives in version 4 repository
        format.  Encoding the structure of a repository into the archive is
        necessary to enable easy composition of package archive contents with
        existing repositories and to enable consumers to access the contents of
        a package archive the same as they would a repository.

        This class can be used to access or extract the contents of almost any
        tar archive, except for those that are compressed.
        """

        __idx_pfx = "pkg5.index."
        __idx_sfx = ".gz"
        __idx_name = "pkg5.index.{0}.gz"
        __idx_ver = ArchiveIndex.CURRENT_VERSION
        __index = None
        __arc_tfile = None
        __arc_file = None
        version = None

        # If the repository format changes, then the version of the package
        # archive format should be rev'd and this updated.  (Although that isn't
        # strictly necessary, as the Repository class should remain backwards
        # compatible with this format.)
        CURRENT_VERSION = 0
        COMPATIBLE_VERSIONS = (0,)

        def __init__(self, pathname, mode="r", archive_index=None):
                """'pathname' is the absolute path of the archive file to create
                or read from.

                'mode' is a string used to indicate whether the archive is being
                opened for reading or writing, which is indicated by 'r' and 'w'
                respectively.  An archive opened for writing may not be used for
                any extraction operations, and must not already exist.

                'archive_index', if supplied is the dictionary returned by
                self.get_index(), allowing multiple Archive objects to be open,
                sharing the same index object, for efficient use of memory.
                Using an existing archive_index requires mode='r'.
                """

                assert os.path.isabs(pathname)
                self.__arc_name = pathname
                self.__closed = False
                self.__mode = mode
                self.__temp_dir = tempfile.mkdtemp()

                # Used to cache publisher objects.
                self.__pubs = None

                # Used to cache location of publisher catalog data.
                self.__catalogs = {}

                arc_mode = mode + "b"
                mode += ":"

                assert "r" in mode or "w" in mode
                assert "a" not in mode
                if "w" in mode:
                        # Don't allow overwrite of existing archive.
                        assert not os.path.exists(self.__arc_name)
                        # Ensure we're not sharing an index object.
                        assert not archive_index

                try:
                        self.__arc_file = open(self.__arc_name, arc_mode,
                            128*1024)
                except EnvironmentError as e:
                        if e.errno in (errno.ENOENT, errno.EISDIR):
                                raise InvalidArchive(self.__arc_name)
                        raise apx._convert_error(e)

                self.__queue_offset = 0
                self.__queue = collections.deque()

                # Ensure cleanup is performed on exit if the archive is not
                # explicitly closed.
                def arc_cleanup():
                        if not self.__closed:
                                self.__close_fh()
                        self.__cleanup()
                        return
                atexit.register(arc_cleanup)

                # Open the pax archive for the package.
                try:
                        self.__arc_tfile = ptf.PkgTarFile.open(mode=mode,
                            fileobj=self.__arc_file, format=tf.PAX_FORMAT)
                except EnvironmentError as e:
                        raise apx._convert_error(e)
                except Exception:
                        # Likely not an archive or the archive is corrupt.
                        raise InvalidArchive(self.__arc_name)

                self.__extract_offsets = {}
                if "r" in mode:
                        # Opening the tarfile loaded the first member, which
                        # should be the archive index file.
                        member = self.__arc_tfile.firstmember
                        if not member:
                                # Archive is empty.
                                raise InvalidArchive(self.__arc_name)

                        # If we have an archive_index use that and return
                        # immediately.  We assume that the caller has obtained
                        # the index from an exising Archive object,
                        # and will have validated the version of that archive.
                        if archive_index:
                                self.__extract_offsets = archive_index
                                return

                        if not member.name.startswith(self.__idx_pfx) or \
                            not member.name.endswith(self.__idx_sfx):
                                return
                        else:
                                self.__idx_name = member.name

                        comment = member.pax_headers.get("comment", "")
                        if not comment.startswith("pkg5.archive.version."):
                                return

                        try:
                                self.version = int(comment.rsplit(".", 1)[-1])
                        except (IndexError, ValueError):
                                raise InvalidArchive(self.__arc_name)

                        if self.version not in self.COMPATIBLE_VERSIONS:
                                raise InvalidArchive(self.__arc_name)

                        # Create a temporary file to extract the index to,
                        # and then extract it from the archive.
                        fobj, idxfn = self.__mkstemp()
                        fobj.close()
                        try:
                                self.__arc_tfile.extract_to(member,
                                    path=self.__temp_dir,
                                    filename=os.path.basename(idxfn))
                        except tf.TarError:
                                # Read error encountered.
                                raise InvalidArchive(self.__arc_name)
                        except EnvironmentError as e:
                                raise apx._convert_error(e)

                        # After extraction, the current archive file offset
                        # is the base that will be used for all other
                        # extractions.
                        index_offset = self.__arc_tfile.offset

                        # Load archive index.
                        try:
                                self.__index = ArchiveIndex(idxfn,
                                    mode="r", version=self.__idx_ver)
                                for name, offset in \
                                    self.__index.offsets():
                                        self.__extract_offsets[name] = \
                                            index_offset + offset
                        except InvalidArchiveIndex:
                                # Index is corrupt; rather than driving on
                                # and failing later, bail now.
                                os.unlink(idxfn)
                                raise InvalidArchive(self.__arc_name)
                        except EnvironmentError as e:
                                raise apx._convert_error(e)

                elif "w" in mode:
                        self.__pubs = {}

                        # Force normalization of archive member mode and
                        # ownership information during archive creation.
                        def gettarinfo(*args, **kwargs):
                                ti = ptf.PkgTarFile.gettarinfo(self.__arc_tfile,
                                    *args, **kwargs)
                                if ti.isreg():
                                        ti.mode = pkg.misc.PKG_FILE_MODE
                                elif ti.isdir():
                                        ti.mode = pkg.misc.PKG_DIR_MODE
                                if ti.name == "pkg5.index.0.gz":
                                        ti.pax_headers["comment"] = \
                                            "pkg5.archive.version.{0:d}".format(
                                            self.CURRENT_VERSION)
                                ti.uid = 0
                                ti.gid = 0
                                ti.uname = "root"
                                ti.gname = "root"
                                return ti
                        self.__arc_tfile.gettarinfo = gettarinfo

                        self.__idx_name = self.__idx_name.format(self.__idx_ver)

                        # Create a temporary file to write the index to,
                        # and then create the index.
                        fobj, idxfn = self.__mkstemp()
                        fobj.close()
                        self.__index = ArchiveIndex(idxfn, mode=arc_mode)

                        # Used to determine what the default publisher will be
                        # for the archive file at close().
                        self.__default_pub = ""

                        # Used to keep track of which package files have already
                        # been added to archive.
                        self.__processed_pfiles = set()

                        # Always create archives using current version.
                        self.version = self.CURRENT_VERSION

                        # Always add base publisher directory to start; tarfile
                        # requires an actual filesystem object to do this, so
                        # re-use an existing directory to do so.
                        self.add("/", arcname="publisher")

        def __exit__(self, exc_type, exc_value, exc_tb):
                """Context handler that ensures archive is automatically closed
                in a non-error condition scenario.  This enables 'with' usage.
                """

                if exc_type or exc_value or exc_tb:
                        # Only close file objects; don't actually write anything
                        # out in an error condition.
                        self.__close_fh()
                        return

                # Close and/or write out archive as needed.
                self.close()

        def __find_extract_offsets(self):
                """Private helper method to find offsets for individual archive
                member extraction.
                """

                if self.__extract_offsets:
                        return

                # This causes the entire archive to be read, but is the only way
                # to find the offsets to extract everything.
                try:
                        for member in self.__arc_tfile.getmembers():
                                self.__extract_offsets[member.name] = \
                                    member.offset
                except tf.TarError:
                        # Read error encountered.
                        raise InvalidArchive(self.__arc_name)
                except EnvironmentError as e:
                        raise apx._convert_error(e)

        def __mkdtemp(self):
                """Creates a temporary directory for use during archive
                operations, and return its absolute path.  The temporary
                directory will be removed after the archive is closed.
                """

                try:
                        return tempfile.mkdtemp(dir=self.__temp_dir)
                except EnvironmentError as e:
                        raise apx._convert_error(e)

        def __mkstemp(self):
                """Creates a temporary file for use during archive operations,
                and returns a file object for it and its absolute path.  The
                temporary file will be removed after the archive is closed.
                """
                try:
                        fd, fn = tempfile.mkstemp(dir=self.__temp_dir)
                        fobj = os.fdopen(fd, "w")
                except EnvironmentError as e:
                        raise apx._convert_error(e)
                return fobj, fn

        def add(self, pathname, arcname=None):
                """Queue the specified object for addition to the archive.
                The archive will be created and the object added to it when the
                close() method is called.  The target object must not change
                after this method is called while the archive is open.  The
                item being added must not already exist in the archive.

                'pathname' is an optional string specifying the absolute path
                of a file to add to the archive.  The file may be a regular
                file, directory, symbolic link, or hard link.

                'arcname' is an optional string specifying an alternative name
                for the file in the archive.  If not given, the full pathname
                provided will be used.
                """

                assert not self.__closed and "w" in self.__mode
                tfile = self.__arc_tfile
                ti = tfile.gettarinfo(pathname, arcname=arcname)
                buf = ti.tobuf(tfile.format, tfile.encoding, tfile.errors)

                # Pre-calculate size of archive entry by determining where
                # in the archive the entry would be added.
                entry_sz = len(buf)
                blocks, rem = divmod(ti.size, tf.BLOCKSIZE)
                if rem > 0:
                        blocks += 1
                entry_sz += blocks * tf.BLOCKSIZE

                # Record name, offset, entry_size, size type for each file.
                self.__index.add(ti.name, self.__queue_offset, entry_sz,
                    ti.size, ti.type)
                self.__queue_offset += entry_sz
                self.__queue.append((pathname, ti.name))

                # Discard tarinfo; it would be more efficient to keep these in
                # memory, but at a significant memory footprint cost.
                ti.tarfile = None
                del ti

        def __add_publisher_files(self, root, file_dir, hashes, fpath=None,
            repo=None):
                """Private helper function for adding package files."""

                if file_dir not in self.__processed_pfiles:
                        # Directory entry needs to be added
                        # for package files.
                        self.add(root, arcname=file_dir)
                        self.__processed_pfiles.add(file_dir)

                for fhash in hashes:
                        hash_dir = os.path.join(file_dir, fhash[:2])
                        if hash_dir not in self.__processed_pfiles:
                                # Directory entry needs to be added
                                # for hash directory.
                                self.add(root, arcname=hash_dir)
                                self.__processed_pfiles.add(hash_dir)

                        hash_fname = os.path.join(hash_dir, fhash)
                        if hash_fname in self.__processed_pfiles:
                                # Already added for a different
                                # package.
                                continue

                        if repo:
                                src = repo.file(fhash)
                        else:
                                src = os.path.join(fpath, fhash)
                        self.add(src, arcname=hash_fname)

                        # A bit expensive potentially in terms of
                        # memory usage, but necessary to prevent
                        # duplicate archive entries.
                        self.__processed_pfiles.add(hash_fname)

        def __add_package(self, pfmri, mpath, fpath=None, repo=None):
                """Private helper function that queues a package for addition to
                the archive.

                'mpath' is the absolute path of the package manifest file.

                'fpath' is an optional directory containing the package files
                stored by hash.

                'repo' is an optional Repository object to use to retrieve the
                data for the package to be added to the archive.

                'fpath' or 'repo' must be provided.
                """

                assert not self.__closed and "w" in self.__mode
                assert mpath
                assert not (fpath and repo)
                assert fpath or repo

                if not self.__default_pub:
                        self.__default_pub = pfmri.publisher

                m = pkg.manifest.Manifest(pfmri)
                m.set_content(pathname=mpath)

                # Throughout this function, the archive root directory is used
                # as a template to add other directories that should be present
                # in the archive.  This is necessary as the tarfile class does
                # not support adding arbitrary archive entries without a real
                # filesystem object as a source.
                root = os.path.dirname(self.__arc_name)
                pub_dir = os.path.join("publisher", pfmri.publisher)
                pkg_dir = os.path.join(pub_dir, "pkg")
                for d in pub_dir, pkg_dir:
                        if d not in self.__processed_pfiles:
                                self.add(root, arcname=d)
                                self.__processed_pfiles.add(d)

                # After manifest has been loaded, assume it's ok to queue the
                # manifest itself for addition to the archive.
                arcname = os.path.join(pkg_dir, pfmri.get_dir_path())

                # Entry may need to be added for manifest directory.
                man_dir = os.path.dirname(arcname)
                if man_dir not in self.__processed_pfiles:
                        self.add(root, arcname=man_dir)
                        self.__processed_pfiles.add(man_dir)

                # Entry needs to be added for manifest file.
                self.add(mpath, arcname=arcname)

                # Now add any files to the archive for every action that has a
                # payload.  (That payload can consist of multiple files.)
                file_dir = os.path.join(pub_dir, "file")
                for a in m.gen_actions():
                        if not a.has_payload:
                                # Nothing to archive.
                                continue

                        pref_hattr, hval, hfunc = \
                            digest.get_least_preferred_hash(a)
                        if not hval:
                                # Nothing to archive
                                continue

                        payloads = set([hval])

                        # Signature actions require special handling.
                        if a.name == "signature":
                                for c in a.get_chain_certs(
                                    least_preferred=True):
                                        payloads.add(c)

                                if repo:
                                        # This bit of logic only possible if
                                        # package source is a repository.
                                        pub = self.__pubs.get(pfmri.publisher,
                                            None)
                                        if not pub:
                                                self.__pubs[pfmri.publisher] = \
                                                    pub = repo.get_publisher(
                                                    pfmri.publisher)
                                                assert pub

                        if not payloads:
                                # Nothing more to do.
                                continue

                        self.__add_publisher_files(root, file_dir, payloads,
                             fpath=fpath, repo=repo)

        def add_package(self, pfmri, mpath, fpath):
                """Queues the specified package for addition to the archive.
                The archive will be created and the package added to it when
                the close() method is called.  The package contents must not
                change after this method is called while the archive is open.

                'pfmri' is the FMRI string or object identifying the package to
                add.

                'mpath' is the absolute path of the package manifest file.

                'fpath' is the directory containing the package files stored
                by hash.
                """

                assert pfmri and mpath and fpath
                if isinstance(pfmri, six.string_types):
                        pfmri = pkg.fmri.PkgFmri(pfmri)
                assert pfmri.publisher
                self.__add_package(pfmri, mpath, fpath=fpath)

        def add_repo_package(self, pfmri, repo):
                """Queues the specified package in a repository for addition to
                the archive. The archive will be created and the package added
                to it when the close() method is called.  The package contents
                must not change after this method is called while the archive is
                open.

                'pfmri' is the FMRI string or object identifying the package to
                add.

                'repo' is the Repository object to use to retrieve the data for
                the package to be added to the archive.
                """

                assert pfmri and repo
                if isinstance(pfmri, six.string_types):
                        pfmri = pkg.fmri.PkgFmri(pfmri)
                assert pfmri.publisher
                self.__add_package(pfmri, repo.manifest(pfmri), repo=repo)

        def extract_catalog1(self, part, path, pub=None):
                """Extract the named v1 catalog part to the specified directory.

                'part' is the name of the catalog file part.

                'path' is the absolute path of the directory to extract the
                file to.  It will be created automatically if it does not
                exist.

                'pub' is an optional publisher prefix.  If not provided, the
                first publisher catalog found in the archive will be used.
                """

                # If the extraction index doesn't exist, scan the
                # complete archive and build one.
                self.__find_extract_offsets()

                pubs = [
                    p for p in self.get_publishers()
                    if not pub or p.prefix == pub
                ]
                if not pubs:
                        raise UnknownArchiveFiles(self.__arc_name, [part])

                if not pub:
                        # Default to first known publisher.
                        pub = pubs[0].prefix

                # Expected locations in archive for various metadata.
                # A trailing slash is appended so that archive entry
                # comparisons skip the entries for the directory.
                pubpath = os.path.join("publisher", pub) + os.path.sep
                catpath = os.path.join(pubpath, "catalog") + os.path.sep
                partpath = os.path.join(catpath, part)

                if pub in self.__catalogs:
                        # Catalog file requested for this publisher before.
                        croot = self.__catalogs[pub]
                        if croot:
                                # Catalog data is cached because it was
                                # generated on demand, so just copy it
                                # from there to the destination.
                                src = os.path.join(croot, part)
                                if not os.path.exists(src):
                                        raise UnknownArchiveFiles(
                                            self.__arc_name, [partpath])

                                try:
                                        pkg.portable.copyfile(
                                            os.path.join(croot, part),
                                            os.path.join(path, part))
                                except EnvironmentError as e:
                                        raise apx._convert_error(e)
                        else:
                                # Use default extraction logic.
                                self.extract_to(partpath, path, filename=part)
                        return

                # Determine whether any catalog files are present for this
                # publisher in the archive.
                for name in self.__extract_offsets:
                        if name.startswith(catpath):
                                # Any catalog file at all means this publisher
                                # should be marked as being known to have one
                                # and then the request passed on to extract_to.
                                self.__catalogs[pub] = None
                                return self.extract_to(partpath, path,
                                    filename=part)

                # No catalog data found for publisher; construct a catalog
                # in memory based on packages found for publisher.
                cat = pkg.catalog.Catalog(batch_mode=True)
                manpath = os.path.join(pubpath, "pkg") + os.path.sep
                lm = None
                for name in self.__extract_offsets:
                        if name.startswith(manpath) and name.count("/") == 4:
                                ignored, stem, ver = name.rsplit("/", 2)
                                stem = unquote(stem)
                                ver = unquote(ver)
                                pfmri = pkg.fmri.PkgFmri(name=stem,
                                    publisher=pub, version=ver)

                                pfmri_tmp_ts = pfmri.get_timestamp()
                                if not lm or lm < pfmri_tmp_ts:
                                        lm = pfmri_tmp_ts

                                fobj = self.get_file(name)
                                m = pkg.manifest.Manifest(pfmri=pfmri)
                                m.set_content(content=force_str(fobj.read()),
                                    signatures=True)
                                cat.add_package(pfmri, manifest=m)

                # Store catalog in a temporary directory and mark publisher
                # as having catalog data cached.
                croot = self.__mkdtemp()
                cat.meta_root = croot
                cat.batch_mode = False
                cat.finalize()
                if lm:
                        cat.last_modified = lm
                cat.save()
                self.__catalogs[pub] = croot

                # Finally, copy requested file to destination.
                try:
                        pkg.portable.copyfile(os.path.join(croot, part),
                            os.path.join(path, part))
                except EnvironmentError as e:
                        raise apx._convert_error(e)

        def extract_package_files(self, hashes, path, pub=None):
                """Extract one or more package files from the archive.

                'hashes' is a list of the files to extract named by their hash.

                'path' is the absolute path of the directory to extract the
                files to.  It will be created automatically if it does not
                exist.

                'pub' is the prefix (name) of the publisher that the package
                files are associated with.  If not provided, the first file
                named after the given hash found in the archive will be used.
                (This will be noticeably slower depending on the size of the
                archive.)
                """

                assert not self.__closed and "r" in self.__mode
                assert hashes

                # If the extraction index doesn't exist, scan the complete
                # archive and build one.
                self.__find_extract_offsets()

                if not pub:
                        # Scan extract offsets index for the first instance of
                        # any package file seen for each hash and extract the
                        # file as each is found.
                        hashes = set(hashes)

                        for name in self.__extract_offsets:
                                for fhash in hashes:
                                        hash_fname = os.path.join("file",
                                            fhash[:2], fhash)
                                        if name.endswith(hash_fname):
                                                self.extract_to(name, path,
                                                    filename=fhash)
                                                hashes.discard(fhash)
                                                break
                                if not hashes:
                                        break

                        if hashes:
                                # Any remaining hashes are for package files
                                # that couldn't be found.
                                raise UnknownArchiveFiles(self.__arc_name,
                                    hashes)
                        return

                for fhash in hashes:
                        arcname = os.path.join("publisher", pub, "file",
                            fhash[:2], fhash)
                        self.extract_to(arcname, path, filename=fhash)

        def extract_package_manifest(self, pfmri, path, filename=""):
                """Extract a package manifest from the archive.

                'pfmri' is the FMRI string or object identifying the package
                manifest to extract.

                'path' is the absolute path of the directory to extract the
                manifest to.  It will be created automatically if it does not
                exist.

                'filename' is an optional name to use for the extracted file.
                If not provided, the default behaviour is to create a directory
                named after the package stem in 'path' and a file named after
                the version in that directory; both components will be URI
                encoded.
                """

                assert not self.__closed and "r" in self.__mode
                assert pfmri and path
                if isinstance(pfmri, six.string_types):
                        pfmri = pkg.fmri.PkgFmri(pfmri)
                assert pfmri.publisher

                if not filename:
                        filename = pfmri.get_dir_path()

                arcname = os.path.join("publisher", pfmri.publisher, "pkg",
                    pfmri.get_dir_path())
                try:
                        self.extract_to(arcname, path, filename=filename)
                except UnknownArchiveFiles:
                        raise UnknownPackageManifest(self.__arc_name, pfmri)

        def extract_to(self, src, path, filename=""):
                """Extract a member from the archive.

                'src' is the pathname of the archive file to extract.

                'path' is the absolute path of the directory to extract the file
                to.

                'filename' is an optional string indicating the name to use for
                the extracted file.  If not provided, the full member name in
                the archive will be used.
                """

                assert not self.__closed and "r" in self.__mode

                # Get the offset in the archive for the given file, and then
                # seek to it.
                offset = self.__extract_offsets.get(src, None)
                tfile = self.__arc_tfile
                if offset is not None:
                        # Prepare the tarfile object for extraction by telling
                        # it where to look for the file.
                        self.__arc_file.seek(offset)
                        tfile.offset = offset

                        # Get the tarinfo object needed to extract the file.
                        try:
                                member = tf.TarInfo.fromtarfile(tfile)
                        except tf.TarError:
                                # Read error encountered.
                                raise InvalidArchive(self.__arc_name)
                        except EnvironmentError as e:
                                raise apx._convert_error(e)

                        if member.name != src:
                                # Index must be invalid or tarfile has gone off
                                # the rails trying to read the archive.
                                raise InvalidArchive(self.__arc_name)

                elif self.__extract_offsets:
                        # Assume there is no such archive member if extract
                        # offsets are known, but the item can't be found.
                        raise UnknownArchiveFiles(self.__arc_name, [src])
                else:
                        # No archive index; fallback to retrieval by name.
                        member = src

                # Extract the file to the specified location.
                try:
                        self.__arc_tfile.extract_to(member, path=path,
                            filename=filename)
                except KeyError:
                        raise UnknownArchiveFiles(self.__arc_name, [src])
                except tf.TarError:
                        # Read error encountered.
                        raise InvalidArchive(self.__arc_name)
                except EnvironmentError as e:
                        raise apx._convert_error(e)

                if not isinstance(member, tf.TarInfo):
                        # Nothing more to do.
                        return

                # If possible, validate the size of the extracted object.
                try:
                        if not filename:
                                filename = member.name
                        dest = os.path.join(path, filename)
                        if os.stat(dest).st_size != member.size:
                                raise CorruptArchiveFiles(self.__arc_name,
                                    [src])
                except EnvironmentError as e:
                        raise apx._convert_error(e)

        def get_file(self, src):
                """Returns an archive member as a file object.  If the matching
                member is a regular file, a file-like object will be returned.
                If it is a link, a file-like object is constructed from the
                link's target.  In all other cases, None will be returned.  The
                file-like object is read-only and provides methods: read(),
                readline(), readlines(), seek() and tell().  The returned object
                must be closed before the archive is, and must not be used after
                the archive is closed.

                'src' is the pathname of the archive file to return.
                """

                assert not self.__closed and "r" in self.__mode

                # Get the offset in the archive for the given file, and then
                # seek to it.
                offset = self.__extract_offsets.get(src, None)
                tfile = self.__arc_tfile
                if offset is not None:
                        # Prepare the tarfile object for extraction by telling
                        # it where to look for the file.
                        self.__arc_file.seek(offset)
                        tfile.offset = offset

                        try:
                                # Get the tarinfo object needed to extract the
                                # file.
                                member = tf.TarInfo.fromtarfile(tfile)
                        except tf.TarError:
                                # Read error encountered.
                                raise InvalidArchive(self.__arc_name)
                elif self.__extract_offsets:
                        # Assume there is no such archive member if extract
                        # offsets are known, but the item can't be found.
                        raise UnknownArchiveFiles(self.__arc_name, [src])
                else:
                        # No archive index; fallback to retrieval by name.
                        member = src

                # Finally, return the object for the matching archive member.
                try:
                        return tfile.extractfile(member)
                except KeyError:
                        raise UnknownArchiveFiles(self.__arc_name, [src])

        def get_index(self):
                """Returns the index, and extract_offsets from an Archive
                opened in read-only mode, allowing additional Archive objects
                to reuse the index, in a memory-efficient manner."""
                assert not self.__closed and "r" in self.__mode
                if not self.__extract_offsets:
                        # If the extraction index doesn't exist, scan the
                        # complete archive and build one.
                        self.__find_extract_offsets()
                return self.__extract_offsets

        def get_package_file(self, fhash, pub=None):
                """Returns the first package file matching the given hash as a
                file-like object. The file-like object is read-only and provides
                methods: read(), readline(), readlines(), seek() and tell().
                The returned object  must be closed before the archive is, and
                must not be used after the archive is closed.

                'fhash' is the hash name of the file to return.

                'pub' is the prefix (name) of the publisher that the package
                files are associated with.  If not provided, the first file
                named after the given hash found in the archive will be used.
                (This will be noticeably slower depending on the size of the
                archive.)
                """

                assert not self.__closed and "r" in self.__mode

                if not self.__extract_offsets:
                        # If the extraction index doesn't exist, scan the
                        # complete archive and build one.
                        self.__find_extract_offsets()

                if not pub:
                        # Scan extract offsets index for the first instance of
                        # any package file seen for the hash and extract it.
                        hash_fname = os.path.join("file", fhash[:2], fhash)
                        for name in self.__extract_offsets:
                                if name.endswith(hash_fname):
                                        return self.get_file(name)
                        raise UnknownArchiveFiles(self.__arc_name, [fhash])

                return self.get_file(os.path.join("publisher", pub, "file",
                    fhash[:2], fhash))

        def get_package_manifest(self, pfmri, raw=False):
                """Returns a package manifest from the archive.

                'pfmri' is the FMRI string or object identifying the package
                manifest to extract.

                'raw' is an optional boolean indicating whether the raw
                content of the Manifest should be returned.  If True,
                a file-like object containing the content of the manifest.
                If False, a Manifest object will be returned.
                """

                assert not self.__closed and "r" in self.__mode
                assert pfmri
                if isinstance(pfmri, six.string_types):
                        pfmri = pkg.fmri.PkgFmri(pfmri)
                assert pfmri.publisher

                arcname = os.path.join("publisher", pfmri.publisher, "pkg",
                    pfmri.get_dir_path())

                try:
                        fobj = self.get_file(arcname)
                except UnknownArchiveFiles:
                        raise UnknownPackageManifest(self.__arc_name, pfmri)

                if raw:
                        return fobj

                m = pkg.manifest.Manifest(pfmri=pfmri)
                m.set_content(content=force_str(fobj.read()), signatures=True)
                return m

        def get_publishers(self):
                """Return a list of publisher objects for all publishers used
                in the archive."""

                if self.__pubs:
                        return list(self.__pubs.values())

                # If the extraction index doesn't exist, scan the complete
                # archive and build one.
                self.__find_extract_offsets()

                # Search through offset index to find publishers
                # in use.
                self.__pubs = {}
                for name in self.__extract_offsets:
                        if name.count("/") == 1 and \
                            name.startswith("publisher/"):
                                ignored, pfx = name.split("/", 1)

                                # See if this publisher has a .p5i file in the
                                # archive (needed for signed packages).
                                p5iname = os.path.join("publisher", pfx,
                                    "pub.p5i")
                                try:
                                        fobj = self.get_file(p5iname)
                                except UnknownArchiveFiles:
                                        # No p5i; that's ok.
                                        pub = pkg.client.publisher.Publisher(
                                            pfx)
                                else:
                                        pubs = pkg.p5i.parse(fileobj=fobj)
                                        assert len(pubs) == 1
                                        pub = pubs[0][0]
                                        assert pub

                                self.__pubs[pfx] = pub

                return list(self.__pubs.values())

        def __cleanup(self):
                """Private helper method to cleanup temporary files."""

                try:
                        if os.path.exists(self.__temp_dir):
                                shutil.rmtree(self.__temp_dir)
                except EnvironmentError as e:
                        raise apx._convert_error(e)

        def __close_fh(self):
                """Private helper method to close filehandles."""

                # Some archives may not have an index.
                if self.__index:
                        self.__index.close()
                        self.__index = None

                # A read error during archive load may cause these to have
                # never been set.
                if self.__arc_tfile:
                        self.__arc_tfile.close()
                        self.__arc_tfile = None

                if self.__arc_file:
                        self.__arc_file.close()
                        self.__arc_file = None
                self.__closed = True

        def close(self, progtrack=None):
                """If mode is 'r', this will close the archive file.  If mode is
                'w', this will write all queued files to the archive and close
                it.  Further operations on the archive are not possible after
                calling this function."""

                assert not self.__closed

                if "w" not in self.__mode:
                        self.__close_fh()
                        self.__cleanup()
                        return

                # Add the standard pkg5.repository file before closing the
                # index.
                fobj, fname = self.__mkstemp()
                fobj.write("[CONFIGURATION]\nversion = 4\n\n"
                    "[publisher]\nprefix = {0}\n\n"
                    "[repository]\nversion = 4\n".format(self.__default_pub))
                fobj.close()
                self.add(fname, arcname="pkg5.repository")

                # If any publisher objects were cached, then there were
                # signed packages present, and p5i information for each
                # must be added to the archive.
                for pub in self.__pubs.values():
                        # A new publisher object is created with a copy of only
                        # the information that's needed for the archive.
                        npub = pkg.client.publisher.Publisher(pub.prefix,
                            alias=pub.alias,
                            revoked_ca_certs=pub.revoked_ca_certs,
                            approved_ca_certs=pub.approved_ca_certs)

                        # Create a p5i file.
                        fobj, fn = self.__mkstemp()
                        pkg.p5i.write(fobj, [npub])
                        fobj.close()

                        # Queue the p5i file for addition to the archive.
                        arcname = os.path.join("publisher", npub.prefix,
                            "pub.p5i")
                        self.add(fn, arcname=arcname)

                # Close the index; no more entries can be added.
                self.__index.close()

                # If a tracker was provided, setup a progress goal.
                idxbytes = 0
                if progtrack:
                        nfiles = len(self.__queue)
                        nbytes = self.__queue_offset
                        try:
                                fs = os.stat(self.__index.pathname)
                                nfiles += 1
                                idxbytes = fs.st_size
                                nbytes += idxbytes
                        except EnvironmentError as e:
                                raise apx._convert_error(e)

                        progtrack.archive_set_goal(
                            os.path.basename(self.__arc_name), nfiles,
                            nbytes)

                # Add the index file to the archive as the first file; it will
                # automatically be marked with a comment identifying the index
                # version.
                tfile = self.__arc_tfile
                tfile.add(self.__index.pathname, arcname=self.__idx_name)
                if progtrack:
                        progtrack.archive_add_progress(1, idxbytes)
                self.__index = None

                # Add all queued files to the archive.
                while self.__queue:
                        src, arcname = self.__queue.popleft()

                        start_offset = tfile.offset
                        tfile.add(src, arcname=arcname, recursive=False)

                        # tarfile caches member information for every item
                        # added by default, which provides fast access to the
                        # archive contents after generation, but isn't needed
                        # here (and uses a significant amount of memory).
                        # Plus popping it off the stack here allows use of
                        # the object's info to provide progress updates.
                        ti = tfile.members.pop()
                        if progtrack:
                                progtrack.archive_add_progress(1,
                                    tfile.offset - start_offset)
                        ti.tarfile = None
                        del ti

                # Cleanup temporary files.
                self.__cleanup()

                # Archive created; success!
                if progtrack:
                        progtrack.archive_done()
                self.__close_fh()

        @property
        def pathname(self):
                """The absolute path of the archive file."""
                return self.__arc_name
