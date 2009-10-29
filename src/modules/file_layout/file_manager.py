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
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

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

import errno
import os

import pkg.portable as portable
import pkg.file_layout.layout as layout

class NeedToModifyReadOnlyFileManager(Exception):
        """This exception is raised when the caller attempts to modify a
        read-only FileManager."""

        def __init__(self, thing_to_change, create="create"):
                """Create a NeedToModifyReadOnlyFileManager exception.

                The "thing_to_change" parameter is the entity that the file
                manager was asked to modify.

                The "create" parameter describes what kind of modification
                was being attempted."""

                self.ent = thing_to_change
                self.create = create

        def __str__(self):
                return _("The FileManager cannot %(cre)s %(ent)s because it "
                    "is configured read-only.") % \
                    { "cre": self.create, "ent":self.ent }


class FMPermissionsException(Exception):
        """This exception is raised when a FileManager does not have the
        permissions to operate as needed on the file system."""

        def __init__(self, filename):
                self.filename = filename

        def __str__(self):
                return _("FileManager was unable to create %s or the "
                    "directories containing it.") % self.filename


class UnrecognizedFilePaths(Exception):
        """This exception is raised when files are found under the FileManager's
        root which cannot be accounted for."""

        def __init__(self, filepaths):
                self.fps = filepaths

        def __str__(self):
                return _("The following paths were found but cannot be "
                    "accounted for by any of the known layouts:\n%s") % \
                    "\n".join(self.fps)


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
                        self.layouts = layouts
                else:
                        self.layouts = layout.get_default_layouts()
                if not os.path.exists(self.root):
                        if self.readonly:
                                raise NeedToModifyReadOnlyFileManager(self.root)
                        try:
                                os.makedirs(self.root)
                        except EnvironmentError, e:
                                if e.errno == errno.EACCES or \
                                    e.errno == errno.EROFS:
                                        raise FMPermissionsException(e.filename)
                                raise

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

        def lookup(self, hashval, opener=False):
                """Find the file for hashval.

                The "hashval" parameter contains the name of the file to be
                found.

                The "opener" parameter determines whether the function will
                return a path or an open file handle."""

                cur_full_path, dest_full_path = self.__select_path(hashval,
                    True)
                if not cur_full_path:
                        return None
                # If the depot isn't readonly and the file isn't in the location
                # that the primary layout thinks it should be, try to move the
                # file into the right place.
                if dest_full_path != cur_full_path and not self.readonly:
                        try:
                                portable.rename(cur_full_path, dest_full_path)
                                os.removedirs(os.path.dirname(cur_full_path))
                                cur_full_path = dest_full_path
                        except EnvironmentError:
                                pass

                if opener:
                        return open(cur_full_path, "rb")
                return cur_full_path

        def insert(self, hashval, src_path):
                """Add the content at "src_path" to the files under the name
                "hashval"."""

                if self.readonly:
                        raise NeedToModifyReadOnlyFileManager(hashval)
                cur_full_path, dest_full_path = \
                    self.__select_path(hashval, True)
                if cur_full_path == dest_full_path:
                        return
                if cur_full_path:
                        try:
                                portable.remove(src_path)
                        except EnvironmentError, e:
                                if e.errno == errno.EACCES or \
                                    e.errno == errno.EROFS:
                                        raise FMPermissionsException(e.filename)
                                raise
                        src_path = cur_full_path
                p_dir = os.path.dirname(dest_full_path)
                try:
                        if not os.path.exists(p_dir):
                                os.makedirs(p_dir)
                        portable.rename(src_path, dest_full_path)
                except EnvironmentError, e:
                        if e.errno == errno.EACCES or e.errno == errno.EROFS:
                                raise FMPermissionsException(e.filename)
                        raise
                if cur_full_path:
                        try:
                                os.removedirs(os.path.dirname(cur_full_path))
                        except EnvironmentError, e:
                                if e.errno == errno.ENOENT or \
                                    e.errno == errno.EEXIST:
                                        pass
                                elif e.errno == errno.EACCES or \
                                    e.errno == errno.EROFS:
                                        raise FMPermissionsException(e.filename)
                                else:
                                        raise
                return

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
                        except EnvironmentError, e:
                                if e.errno == errno.ENOENT or \
                                    e.errno == errno.EEXIST:
                                        pass
                                elif e.errno == errno.EACCES or \
                                    e.errno == errno.EROFS:
                                        raise FMPermissionsException(e.filename)
                                else:
                                        raise
                return

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
