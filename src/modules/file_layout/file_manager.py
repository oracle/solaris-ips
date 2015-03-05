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
# Copyright (c) 2009, 2015, Oracle and/or its affiliates. All rights reserved.

"""centralized object for insert, lookup, and removal of files.

The purpose of the FileManager class is to provide a central location to
insert, lookup, and remove files, stored in the download directory of the
client or the file directory of the repo.  It provides a way to change the
way files are placed into the directory structure by allowing for an ordered
sequence of layouts.  The FileManager overlays the layouts on top of each
other.  This means that layouts have certain requirements (described in the
layout module), but allows the reuse of shared directory structures when
possible.  When a file is inserted, it is placed in the directory structure
according to the first layout.  When a file is retrieved, each layout is
checked in turn to determine whether the file is present.  If the file is
present but not located according to where it should be located according to
the first layout and the FileManager has permission to move the file, it
wil be moved to that location.  When a file is removed, the layouts are
checked in turn until a file is found and removed.  The FileManager also
provides a way to generate all hashes stored by the FileManager."""

import collections
import errno
import os

import pkg.client.api_errors as apx
import pkg.portable as portable
import pkg.file_layout.layout as layout

class NeedToModifyReadOnlyFileManager(apx.ApiException):
        """This exception is raised when the caller attempts to modify a
        read-only FileManager."""

        def __init__(self, thing_to_change, create="create"):
                """Create a NeedToModifyReadOnlyFileManager exception.

                The "thing_to_change" parameter is the entity that the file
                manager was asked to modify.

                The "create" parameter describes what kind of modification
                was being attempted."""

                apx.ApiException.__init__(self)
                self.ent = thing_to_change
                self.create = create

        def __str__(self):
                return _("The FileManager cannot {cre} {ent} because it "
                    "is configured read-only.").format(
                    cre=self.create, ent=self.ent)


class FMInsertionFailure(apx.ApiException):
        """Used to indicate that an in-progress insert failed because the
        item to be inserted went missing during the operation and wasn't
        already found in the cache."""

        def __init__(self, src, dest):
                apx.ApiException.__init__(self)
                self.src = src
                self.dest = dest

        def __str__(self):
                return _("{src} was removed while FileManager was attempting "
                    "to insert it into the cache as {dest}.").format(
                    **self.__dict__)


class FMPermissionsException(apx.PermissionsException):
        """This exception is raised when a FileManager does not have the
        permissions to operate as needed on the file system."""

        def __str__(self):
                return _("FileManager was unable to create {0} or the "
                    "directories containing it.").format(self.path)


class UnrecognizedFilePaths(apx.ApiException):
        """This exception is raised when files are found under the FileManager's
        root which cannot be accounted for."""

        def __init__(self, filepaths):
                apx.ApiException.__init__(self)
                self.fps = filepaths

        def __str__(self):
                return _("The following paths were found but cannot be "
                    "accounted for by any of the known layouts:\n{0}").format(
                    "\n".join(self.fps))


class FileManager(object):
        """The FileManager class handles the insertion and removal of files
        within its directory according to a strategy for organizing the
        files."""

        def __init__(self, root, readonly, layouts=None):
                """Initialize the FileManager object.

                The "root" parameter is a path to the directory to manage.

                The "readonly" parameter determines whether files can be
                inserted, removed, or moved."""

                if not root:
                        raise ValueError("root must not be none")
                self.root = root
                self.readonly = readonly
                if layouts is not None:
                        if not isinstance(layouts, collections.Iterable):
                                layouts = [layouts]
                        self.layouts = layouts
                else:
                        self.layouts = layout.get_default_layouts()

        def set_read_only(self):
                """Make the FileManager read only."""
                self.readonly = True

        def __select_path(self, hashval, check_existence):
                """Find the path to the file with name hashval.

                The "hashval" parameter is the name of the file to find.

                The "check_existence" parameter determines whether the function
                will ensure that a file exists at the returned path."""

                cur_path = None
                cur_full_path = None
                dest_full_path = None
                for l in self.layouts:
                        cur_path = l.lookup(hashval)
                        cur_full_path = os.path.join(self.root, cur_path)
                        # The first layout in self.layouts is the desired
                        # location.  If that location has not been stored,
                        # record it.
                        if dest_full_path is None:
                                dest_full_path = cur_full_path
                        if not check_existence or os.path.exists(cur_full_path):
                                return cur_full_path, dest_full_path
                return None, dest_full_path

        def lookup(self, hashval, opener=False, check_existence=True):
                """Find the file for hashval.

                The "hashval" parameter contains the name of the file to be
                found.

                The "opener" parameter determines whether the function will
                return a path or an open file handle."""

                cur_full_path, dest_full_path = self.__select_path(hashval,
                    check_existence)
                if not cur_full_path:
                        return None

                # If the depot isn't readonly and the file isn't in the location
                # that the primary layout thinks it should be, try to move the
                # file into the right place.
                if dest_full_path != cur_full_path and not self.readonly:
                        p_sdir = os.path.dirname(cur_full_path)
                        try:
                                # Attempt to move the file from the old location
                                # to the preferred location.
                                try:
                                        portable.rename(cur_full_path,
                                            dest_full_path)
                                except OSError as e:
                                        if e.errno != errno.ENOENT:
                                                raise

                                        p_ddir = os.path.dirname(
                                            dest_full_path)
                                        if os.path.isdir(p_ddir):
                                                raise

                                        try:
                                                os.makedirs(p_ddir)
                                        except EnvironmentError as e:
                                                if e.errno == errno.EACCES or \
                                                    e.errno == errno.EROFS:
                                                        raise FMPermissionsException(
                                                            e.filename)
                                                # If directory creation failed
                                                # due to EEXIST, but the entry
                                                # it failed for isn't the
                                                # immediate parent, assume
                                                # there's a larger problem
                                                # and re-raise the exception.
                                                # For file_manager, this is
                                                # believed to be unlikely.
                                                if not (e.errno == errno.EEXIST and
                                                    e.filename == p_ddir):
                                                        raise

                                        portable.rename(cur_full_path,
                                            dest_full_path)

                                # Since the file has been moved, point at the
                                # new destination *before* attempting to remove
                                # the (now possibly empty) parent directory of
                                # of the source file.
                                cur_full_path = dest_full_path

                                # This may fail because other files can still
                                # exist in the parent path for the source, so
                                # must be done last.
                                os.removedirs(p_sdir)
                        except EnvironmentError:
                                # If there's an error during these operations,
                                # check that cur_full_path still exists.  If
                                # it's gone, return None.
                                if not os.path.exists(cur_full_path):
                                        return None

                if opener:
                        return open(cur_full_path, "rb")
                return cur_full_path

        def insert(self, hashval, src_path):
                """Add the content at "src_path" to the files under the name
                "hashval".  Returns the path to the inserted file."""

                if self.readonly:
                        raise NeedToModifyReadOnlyFileManager(hashval)
                cur_full_path, dest_full_path = \
                    self.__select_path(hashval, True)

                if cur_full_path and cur_full_path != dest_full_path:
                        # The file is stored in an old location and needs to be
                        # moved to a new location.  To prevent disruption of
                        # service or other race conditions, rename the source
                        # file into the old place first.
                        try:
                                portable.rename(src_path, cur_full_path)
                        except EnvironmentError as e:
                                if e.errno == errno.EACCES or \
                                    e.errno == errno.EROFS:
                                        raise FMPermissionsException(e.filename)
                                raise
                        src_path = cur_full_path

                while True:
                        try:
                                # Move the file into place.
                                portable.rename(src_path, dest_full_path)
                        except EnvironmentError as e:
                                p_dir = os.path.dirname(dest_full_path)
                                if e.errno == errno.ENOENT and \
                                    not os.path.isdir(p_dir):
                                        try:
                                                os.makedirs(p_dir)
                                        except EnvironmentError as e:
                                                if e.errno == errno.EACCES or \
                                                    e.errno == errno.EROFS:
                                                        raise FMPermissionsException(
                                                            e.filename)
                                                # If directory creation failed
                                                # due to EEXIST, but the entry
                                                # it failed for isn't the
                                                # immediate parent, assume
                                                # there's a larger problem and
                                                # re-raise the exception.  For
                                                # file_manager, this is believed
                                                # to be unlikely.
                                                if not (e.errno == errno.EEXIST
                                                    and e.filename == p_dir):
                                                        raise

                                        # Parent directory created successsfully
                                        # so loop again to retry rename.
                                elif e.errno == errno.ENOENT and \
                                    not os.path.exists(src_path):
                                        if os.path.exists(dest_full_path):
                                                # Item has already been moved
                                                # into cache by another process;
                                                # nothing more to do.  (This
                                                # could happen during parallel
                                                # publication.)
                                                return dest_full_path
                                        raise FMInsertionFailure(src_path,
                                            dest_full_path)
                                elif e.errno == errno.EACCES or \
                                    e.errno == errno.EROFS:
                                        raise FMPermissionsException(e.filename)
                                elif e.errno != errno.ENOENT:
                                        raise apx._convert_error(e)
                        else:
                                # Success!
                                break

                # Attempt to remove the parent directory of the file's original
                # location to ensure empty directories aren't left behind.
                if cur_full_path:
                        try:
                                os.removedirs(os.path.dirname(cur_full_path))
                        except EnvironmentError as e:
                                if e.errno == errno.ENOENT or \
                                    e.errno == errno.EEXIST:
                                        pass
                                elif e.errno == errno.EACCES or \
                                    e.errno == errno.EROFS:
                                        raise FMPermissionsException(e.filename)
                                else:
                                        raise

                # Return the location of the inserted file to the caller.
                return dest_full_path

        def remove(self, hashval):
                """This function removes the file associated with the name
                "hashval"."""

                if self.readonly:
                        raise NeedToModifyReadOnlyFileManager(hashval,
                            "remove")
                for l in self.layouts:
                        cur_path = l.lookup(hashval)
                        cur_full_path = os.path.join(self.root, cur_path)
                        try:
                                portable.remove(cur_full_path)
                                os.removedirs(os.path.dirname(cur_full_path))
                        except EnvironmentError as e:
                                if e.errno == errno.ENOENT or \
                                    e.errno == errno.EEXIST:
                                        pass
                                elif e.errno == errno.EACCES or \
                                    e.errno == errno.EROFS:
                                        raise FMPermissionsException(e.filename)
                                else:
                                        raise

        def walk(self):
                """Generate all the hashes of all files known."""

                unrecognized = []
                for dirpath, dirnames, filenames in os.walk(self.root):
                        for fn in filenames:
                                fp = os.path.join(dirpath, fn)
                                fp = fp[len(self.root):].lstrip(os.path.sep)
                                for l in self.layouts:
                                        if l.contains(fp, fn):
                                                yield l.path_to_hash(fp)
                                                break
                                else:
                                        unrecognized.append(fp)
                if unrecognized:
                        raise UnrecognizedFilePaths(unrecognized)
