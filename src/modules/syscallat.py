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
# Copyright (c) 2015, Oracle and/or its affiliates. All rights reserved.
#

from __future__ import unicode_literals
import os
import six
from pkg._syscallat import lib, ffi


def mkdirat(fd, path, mode):
    """Invoke mkdirat(2)."""

    if not isinstance(fd, int):
        raise TypeError("fd must be int type")
    if not isinstance(path, six.string_types):
        raise TypeError("path must be a string")
    if not isinstance(mode, int):
        raise TypeError("mode must be int type")

    rv = lib.mkdirat(fd, path, mode)
    if rv != 0:
        raise OSError(ffi.errno, os.strerror(ffi.errno), path)


def openat(fildes, path, oflag, mode):
    """Invoke openat(2)."""

    if not isinstance(fildes, int):
        raise TypeError("fildes must be int type")
    if not isinstance(path, six.string_types):
        raise TypeError("path must be a string")
    if not isinstance(oflag, int):
        raise TypeError("oflag must be int type")
    if not isinstance(mode, int):
        raise TypeError("mode must be int type")

    rv = lib.openat(fildes, path, oflag, mode)
    if rv < 0:
        raise OSError(ffi.errno, os.strerror(ffi.errno), path)
    return rv


def renameat(fromfd, old, tofd, new):
    """Invoke renameat(2)."""

    if not isinstance(fromfd, int):
        raise TypeError("fromfd must be int type")
    if not isinstance(old, six.string_types):
        raise TypeError("old must be a string")
    if not isinstance(tofd, int):
        raise TypeError("tofd must be int type")
    if not isinstance(new, six.string_types):
        raise TypeError("new must be a string")

    rv = lib.renameat(fromfd, old, tofd, new)
    if rv != 0:
        raise OSError(ffi.errno, os.strerror(ffi.errno), old)


def unlinkat(dirfd, path, flag):
    """Invoke unlinkat(2)."""

    if not isinstance(dirfd, int):
        raise TypeError("dirfd must be int type")
    if not isinstance(path, six.string_types):
        raise TypeError("path must be a string")
    if not isinstance(flag, int):
        raise TypeError("flag must be int type")

    rv = lib.unlinkat(dirfd, path, flag)
    if rv < 0:
        raise OSError(ffi.errno, os.strerror(ffi.errno), path)
