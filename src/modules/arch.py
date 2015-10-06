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
from pkg._arch import lib, ffi

NULL = ffi.NULL


def _get_sysinfo(sicmd):
    ret = 0
    bufsz = 32
    buf = lib.malloc(bufsz)
    buf = ffi.gc(buf, lib.free)
    if buf == NULL:
        return NULL

    while True:
        ret = lib.sysinfo(sicmd, buf, bufsz)
        if ret < 0:
            return NULL
        if ret > bufsz:
            bufsz = ret
            tmp = lib.realloc(buf, bufsz)
            tmp = ffi.gc(tmp, lib.free)
            if tmp == NULL:
                return NULL
            buf = tmp
        else:
            break
        if buf == NULL:
            break

    return buf


def get_isainfo():
    """Return a list of strings constituting the architecture tags for the
    invoking system."""
    buf = NULL
    buf1 = _get_sysinfo(lib.SI_ARCHITECTURE_64)
    buf2 = _get_sysinfo(lib.SI_ARCHITECTURE_32)

    if buf1 == NULL and buf2 == NULL:
        return
    if buf1 == NULL and buf2:
        buf = buf2
    if buf2 == NULL and buf1:
        buf = buf1

    from pkg.misc import bytes_to_unicode
    # ffi.string returns a bytes
    if buf == NULL:
        buf1 = bytes_to_unicode(ffi.string(ffi.cast("char *", buf1)))
        buf2 = bytes_to_unicode(ffi.string(ffi.cast("char *", buf2)))
        robj = [buf1, buf2]
    else:
        buf = bytes_to_unicode(ffi.string(ffi.cast("char *", buf)))
        robj = [buf]

    return robj


def get_release():
    """Return the release string ("5.11") for the invoking system."""
    buf = _get_sysinfo(lib.SI_RELEASE)
    if buf == NULL:
        return
    from pkg.misc import bytes_to_unicode
    return bytes_to_unicode(ffi.string(ffi.cast("char *", buf)))


def get_platform():
    """Return the platform tag ("i86pc") for the invoking system."""
    buf = _get_sysinfo(lib.SI_PLATFORM)
    if buf == NULL:
        return
    from pkg.misc import bytes_to_unicode
    return bytes_to_unicode(ffi.string(ffi.cast("char *", buf)))
