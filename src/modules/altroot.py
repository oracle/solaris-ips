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
# Copyright (c) 2011, 2015, Oracle and/or its affiliates. All rights reserved.
#

"""
Generic interfaces for manipulating files in an alternate root.  There
routines guarantee that if you perform operations on a specified path, and
that path is contained within "root", then those operations will not affect
any files living outside of "root".  These routines mainly protect us when
accessing paths which could contain symbolic links which might otherwise
redirect us to an unexpected file system object.
"""

# standard python classes
import errno
import os
import stat

# pkg classes
#
# pkg.syscallat is only needed until we have a newer version of python which
# has native support for all the *at(2) system calls we use below.
import pkg.syscallat as sat

# ---------------------------------------------------------------------------
# Misc Functions
#
def __path_abs_to_relative(path):
        """Strip the leading '/' from a path using os.path.split()."""

        path_new = None
        while True:
                (path, tail) = os.path.split(path)
                if not tail:
                        break
                if path_new:
                        path_new = os.path.join(tail, path_new)
                else:
                        path_new = tail
        return path_new

def __fd_to_path(fd):
        """Given a file descriptor return the path to that file descriptor."""

        path = "/proc/{0:d}/path/{1:d}".format(os.getpid(), fd)
        return os.readlink(path)

# ---------------------------------------------------------------------------
# Functions for accessing files in an alternate image
#
def ar_open(root, path, flags,
    mode=None, create=False, truncate=False):
        """A function similar to os.open() that ensures that the path
        we're accessing resides within a specified directory subtree.

        'root' is a directory that path must reside in.

        'path' is a path that is interpreted relative to 'root'.  i.e., 'root'
        is prepended to path.  'path' can not contain any symbolic links that
        would cause an access to be redirected outside of 'root'.  If this
        happens we'll raise an OSError exception with errno set to EREMOTE

        'mode' optional permissions mask used if we create 'path'

        'create' optional flag indicating if we should create 'path'

        'truncate' optional flag indicating if we should truncate 'path' after
        opening it."""

        # all paths must be absolute
        assert os.path.isabs(root)

        # only allow read/write flags
        assert (flags & ~(os.O_WRONLY|os.O_RDONLY)) == 0

        # we can't truncate a file unless we open it for writing
        assert not truncate or (flags & os.O_WRONLY)

        # if create is true the user must supply a mode mask
        assert not create or mode != None

        # we're going to update root and path so prepare an error
        # message with the existing values now.
        eremote = _("Path outside alternate root: root={root}, "
            "path={path}").format(root=root, path=path)

        # make target into a relative path
        if os.path.isabs(path):
                path = __path_abs_to_relative(path)

        # now open the alternate root and get its path
        # done to eliminate any links/mounts/etc in the path
        root_fd = os.open(root, os.O_RDONLY)
        try:
                root = __fd_to_path(root_fd)
        except OSError as e:
                if e.errno != errno.ENOENT:
                        os.close(root_fd)
                        raise e
        os.close(root_fd)

        # now open the target file, get its path, and make sure it
        # lives in the alternate root
        path_fd = None
        try:
                path_tmp = os.path.join(root, path)
                path_fd = os.open(path_tmp, flags)
        except OSError as e:
                if e.errno != errno.ENOENT or not create:
                        raise e

        assert path_fd or create
        if not path_fd:
                # the file doesn't exist so we should try to create it.
                # we'll do this by first opening the directory which
                # will contain the file and then using openat within
                # that directory.
                path_dir = os.path.dirname(path)
                path_file = os.path.basename(path)
                try:
                        path_dir_fd = \
                            ar_open(root, path_dir, os.O_RDONLY)
                except OSError as e:
                        if e.errno != errno.EREMOTE:
                                raise e
                        raise OSError(errno.EREMOTE, eremote)

                # we opened the directory, now create the file
                try:
                        path_fd = sat.openat(path_dir_fd, path_file,
                            flags|os.O_CREAT|os.O_EXCL, mode)
                except OSError as e:
                        os.close(path_dir_fd)
                        raise e

                # we created the file
                assert path_fd
                os.close(path_dir_fd)

        # verify that the file we opened lives in the alternate root
        try:
                path = __fd_to_path(path_fd)
        except OSError as e:
                if e.errno != errno.ENOENT:
                        os.close(path_fd)
                        raise e
                path = os.path.join(root, path)

        if not path.startswith(root):
                os.close(path_fd)
                raise OSError(errno.EREMOTE, eremote)

        if truncate:
                # the user wanted us to truncate the file
                try:
                        os.ftruncate(path_fd, 0)
                except OSError as e:
                        os.close(path_fd)
                        raise e

        return path_fd

def ar_unlink(root, path, noent_ok=False):
        """A function similar to os.unlink() that ensures that the path
        we're accessing resides within a specified directory subtree.

        'noent_ok' optional flag indicating if it's ok for 'path' to be
        missing.

        For all other parameters, refer to the 'ar_open' function
        for an explanation of their usage and effects."""

        # all paths must be absolute
        assert os.path.isabs(root)

        # make target into a relative path
        if os.path.isabs(path):
                path = __path_abs_to_relative(path)

        path_dir = os.path.dirname(path)
        path_file = os.path.basename(path)

        try:
                path_dir_fd = ar_open(root, path_dir, os.O_RDONLY)
        except OSError as e:
                if noent_ok and e.errno == errno.ENOENT:
                        return
                raise e

        try:
                sat.unlinkat(path_dir_fd, path_file, 0)
        except OSError as e:
                os.close(path_dir_fd)
                if noent_ok and e.errno == errno.ENOENT:
                        return
                raise e

        os.close(path_dir_fd)
        return

def ar_rename(root, src, dst):
        """A function similar to os.rename() that ensures that the path
        we're accessing resides within a specified directory subtree.

        'src' and 'dst' are paths that are interpreted relative to 'root'.
        i.e., 'root' is prepended to both.  'src' and 'dst' can not contain
        any symbolic links that would cause an access to be redirected outside
        of 'root'.  If this happens we'll raise an OSError exception with
        errno set to EREMOTE

        For all other parameters, refer to the 'ar_open' function
        for an explanation of their usage and effects."""

        # all paths must be absolute
        assert os.path.isabs(root)

        # make target into a relative path
        if os.path.isabs(src):
                src = __path_abs_to_relative(src)
        if os.path.isabs(dst):
                dst = __path_abs_to_relative(dst)

        src_dir = os.path.dirname(src)
        src_file = os.path.basename(src)
        dst_dir = os.path.dirname(dst)
        dst_file = os.path.basename(dst)

        src_dir_fd = ar_open(root, src_dir, os.O_RDONLY)
        try:
                dst_dir_fd = ar_open(root, dst_dir, os.O_RDONLY)
        except OSError as e:
                os.close(src_dir_fd)
                raise e

        try:
                sat.renameat(src_dir_fd, src_file, dst_dir_fd, dst_file)
        except OSError as e:
                os.close(src_dir_fd)
                os.close(dst_dir_fd)
                raise e

        os.close(src_dir_fd)
        os.close(dst_dir_fd)
        return

def ar_mkdir(root, path, mode):
        """A function similar to os.mkdir() that ensures that the path we're
        opening resides within a specified directory subtree.

        For all other parameters, refer to the 'ar_open' function
        for an explanation of their usage and effects."""

        # all paths must be absolute
        assert os.path.isabs(root)

        # make target into a relative path
        if os.path.isabs(path):
                path = __path_abs_to_relative(path)

        path_dir = os.path.dirname(path)
        path_file = os.path.basename(path)

        path_dir_fd = ar_open(root, path_dir, os.O_RDONLY)
        try:
                sat.mkdirat(path_dir_fd, path_file, mode)
        except OSError as e:
                os.close(path_dir_fd)
                raise e

        os.close(path_dir_fd)
        return

def ar_stat(root, path):
        """A function similar to os.stat() that ensures that the path
        we're accessing resides within a specified directory subtree.

        For all other parameters, refer to the 'ar_open' function
        for an explanation of their usage and effects."""

        try:
                fd = ar_open(root, path, os.O_RDONLY)
        except OSError as e:
                raise e
        si = os.fstat(fd)
        os.close(fd)
        return si

def ar_isdir(root, path):
        """A function similar to os.path.isdir() that ensures that the path
        we're accessing resides within a specified directory subtree.

        For all other parameters, refer to the 'ar_open' function
        for an explanation of their usage and effects."""

        try:
                si = ar_stat(root, path)
        except OSError as e:
                if e.errno == errno.ENOENT:
                        return False
                raise e

        if stat.S_ISDIR(si.st_mode):
                return True
        return False

def ar_exists(root, path):
        """A function similar to os.path.exists() that ensures that the path
        we're accessing resides within a specified directory subtree.

        For all other parameters, refer to the 'ar_open' function
        for an explanation of their usage and effects."""

        try:
                fd = ar_open(root, path, os.O_RDONLY)
        except OSError as e:
                if e.errno == errno.ENOENT:
                        return False
                raise e
        os.close(fd)
        return True

def ar_diff(root, path1, path2):
        """A function similar to filecmp.cmp() that ensures that the path
        we're accessing resides within a specified directory subtree.

        For all other parameters, refer to the 'ar_open' function
        for an explanation of their usage and effects."""

        fd1 = fd2 = None

        diff = False
        try:
                fd1 = ar_open(root, path1, os.O_RDONLY)
                fd2 = ar_open(root, path2, os.O_RDONLY)

                while True:
                        b1 = os.read(fd1, 1024)
                        b2 = os.read(fd2, 1024)
                        if len(b1) == 0 and len(b2) == 0:
                                # we're done
                                break
                        if len(b1) != len(b2) or b1 != b2:
                                diff = True
                                break
        except OSError as e:
                if fd1:
                        os.close(fd1)
                if fd2:
                        os.close(fd2)
                raise e

        os.close(fd1)
        os.close(fd2)
        return diff

def ar_img_prefix(root):
        """A function that attempts to determine if a user or root pkg(5)
        managed image can be found at 'root'.  If 'root' does point to a
        pkg(5) image, then we return the relative path to the image metadata
        directory."""

        import pkg.client.image as image

        user_img = False
        root_img = False

        if ar_isdir(root, image.img_user_prefix):
                user_img = True

        if ar_isdir(root, image.img_root_prefix):
                root_img = True

        if user_img and root_img:
                #
                # why would an image have two pkg metadata directories.
                # is this image corrupt?
                #
                return None
        if user_img:
                return image.img_user_prefix
        if root_img:
                return image.img_root_prefix
        return None
