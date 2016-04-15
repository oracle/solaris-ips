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
# Copyright (c) 2008, 2016, Oracle and/or its affiliates. All rights reserved.
#

"""
Windows has a specific implementation for most of these.  For the
group and user id-related (credential) APIs, no implementation
is provided.  This causes the file and directory actions to not
utilize any credential metadata when acting on Windows-compatible
systems. In the future, this may be able to be mapped onto the
NTFS group mechanism if deemed useful.
"""

import getpass
import shutil
import os
import errno
import stat
import tempfile
import threading
from . import util as os_util

def get_isainfo():
        """ TODO: Detect Windows 64-bit"""
        return ['i386']

def get_release():
        return os_util.get_os_release()

def get_platform():
        """ TODO: any other windows platforms to support?"""
        return 'i86pc'

def get_group_by_name(name, dirpath, use_file):
        """group names/numbers are ignored on Windows."""
        return -1

def get_user_by_name(name, dirpath, use_file):
        """group names/numbers are ignored on Windows."""
        return -1

def get_name_by_gid(gid, dirpath, use_file):
        """group names/numbers are ignored on Windows."""
        return ''

def get_name_by_uid(uid, dirpath, use_file):
        """group names/numbers are ignored on Windows."""
        return ''

def get_usernames_by_gid(gid, dirpath, use_file):
        """group names/numbers are ignored on Windows."""
        return []

def get_userid():
        """group names/numbers are ignored on Windows."""
        return -1

def get_username():
        try:
                return getpass.getuser()
        except ImportError:
                # getpass.getuser() will fail on systems without
                # pwd module, so try a common python windows add-on
                try:
                        import win32api
                        return win32api.GetUserName()
                except ImportError:
                        return None

def is_admin():
        try:
                # ctypes only available in python 2.5 or later
                import ctypes
                return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except ImportError:
                return False

def chown(path, owner, group):
        """
        group names/numbers are ignored on Windows, so changing
        ownership of a file makes no sense.
        """
        return

# On Windows, rename to existing file is not allowed, so the
# destination file must be deleted first. But if the destination file 
# is locked, it cannot be deleted. Windows has 3 types of file locking
# 
# 1. Using share access controls that allow applications to specify 
#    whole-file access sharing for read, write or delete;
# 2. Using byte range locks to arbitrate read and write access to 
#    regions within a single file; and
# 3. By Windows file systems disallowing executing files from being 
#    opened for write or delete access.
#
# The code here deals only with locks of type 3. If the lock on the open 
# file is for a running executable, then the destination file can be renamed
# and deleted later when the file is no longer in use. For a rename to a 
# destination locked with type 1 or 2, rename throws an OSError exception.
#
# To accomplish the delayed delete, the file is renamed to a trash folder
# within the image containing the file. A single image is assumed to be 
# contained within a single file system, thus making the rename feasible. 
# The empty_trash method is called at the end of rename to cleanup any 
# trash files that were left from earlier calls to rename, typically by 
# previous processes. The empty_trash method needs to be fast most of the 
# time, so the real work is only done the first time a rename operation is 
# done on an image. The image module cannot be imported when this module is
# initialized because that leads to a circular dependency.  So it is imported
# as needed.
        
trashname = "trash"

# cached_image_info is a list of tuples (image root, image trash directory) for
# all of the images that have been accessed by this process. It is used to
# quickly find the trash directory for a path without having to create an
# image object for it each time.
cached_image_info = []
cache_lock = threading.Lock()

def get_trashdir(path):
        """
        Use path to determine the trash directory.  This method does not create
        the directory. If path is not contained within an image, return None.
        The directories for the images that have already been accessed are
        cached to improve the speed of this method.
        """
        global cached_image_info
        global cache_lock
        import pkg.client.image as image
        from pkg.client.api_errors import ImageNotFoundException
        try:
            cache_lock.acquire()
            for iroot, itrash in cached_image_info:
                    if path.startswith(iroot):
                            return itrash

            try:
                    img = image.Image(os.path.dirname(path),
                        allow_ondisk_upgrade=False)
            except ImageNotFoundException:
                    # path is not within an image, no trash dir
                    return None
            trashdir = os.path.join(img.imgdir, trashname)
            # this is the first time putting something in the trash for
            # this image, so try to empty the trash first
            shutil.rmtree(trashdir, True)
            cached_image_info.append((img.get_root(), trashdir))
            return trashdir
        finally:
            cache_lock.release()

def move_to_trash(path):
        """
        Move the file to a trash folder within its containing image. If the 
        file is not in an image, just return without moving it. If the file
        cannot be removed, raise an OSError exception.
        """
        trashdir = get_trashdir(path)
        if not trashdir:
                return
        if not os.path.exists(trashdir):
                os.mkdir(trashdir)
        tdir = tempfile.mkdtemp(dir = trashdir)
        # this rename will raise an exception if the file is
        # locked and cannot be renamed.
        os.rename(path, os.path.join(tdir, os.path.basename(path)))

def rename(src, dst):
        """
        Rename the src file to the dst name, deleting dst if necessary.
        """
        try:
                os.rename(src, dst)
        except OSError as err:
                if err.errno != errno.EEXIST:
                        raise
                try:
                        os.unlink(dst)
                except OSError:
                        move_to_trash(dst)
                # finally rename the file
                os.rename(src, dst)

def remove(path):
        """
        Remove the given path. The file is moved to the trash area of the
        image if necessary where it will be removed at a later time.
        """
        try:
                os.unlink(path)
        except OSError as err:
                if err.errno != errno.EACCES:
                        raise
                move_to_trash(path)

def link(src, dst):
        copyfile(src, dst)
        
def split_path(path):
        drivepath = os.path.splitdrive(path)
        return drivepath[1].split('\\')

def get_root(path):
        drivepath = os.path.splitdrive(path)
        if drivepath[0] == "":
                return os.path.sep
        else:
                return drivepath[0] + '\\'

def assert_mode(path, mode):
        # only compare user's permission bits on Windows
        fmode = stat.S_IMODE(os.lstat(path).st_mode)
        if (mode & stat.S_IRWXU) != (fmode & stat.S_IRWXU):
                ae = AssertionError("mode mismatch for {0}, has {1:o}, "
                    "want {2:o}".format(path, fmode, mode))
                ae.mode = fmode;
                raise ae

def copyfile(src, dst):
        shutil.copyfile(src, dst)
