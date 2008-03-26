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
import tempfile
import util as os_util

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

def rename(src, dst):
        """
        On Windows, rename to existing file is not allowed, so we
        must delete destination first. but if file is open, unlink
        schedules it for delete but does not delete it. rename
        happens immediately even for open files, so we create
        temporary file, delete it, rename destination to that name,
        then delete that. then rename is safe to do.
        """
        try:
                os.rename(src, dst)
        except OSError, err:
                if err == errno.ENOENT:
                        raise
                fd, temp = tempfile.mkstemp(dir=os.path.dirname(dst) or '.')
                os.close(fd)
                os.unlink(temp)
                os.rename(dst, temp)
                os.unlink(temp)
                os.rename(src, dst)

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

def copyfile(src, dst):
        shutil.copyfile(src, dst)
