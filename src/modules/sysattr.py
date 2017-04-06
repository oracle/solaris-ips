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
from pkg._sysattr import lib, ffi

F_ATTR_ALL = lib.F_ATTR_ALL


def is_supported(attr):
    """Test if a sys attr is not in the list of ignored attributes."""

    ignore = [lib.F_OWNERSID, lib.F_GROUPSID, lib.F_AV_SCANSTAMP,
              lib.F_OPAQUE, lib.F_CRTIME, lib.F_FSID, lib.F_GEN, lib.F_REPARSE]

    for i in ignore:
        if i == attr:
            return False
    return True


def fgetattr(filename, compact=False):
    """Get the list of set system attributes for file specified by 'path'.
    Returns a list of verbose attributes by default. If 'compact' is True,
    return a string consisting of compact option identifiers."""

    from pkg.misc import force_text
    if not isinstance(filename, six.string_types):
        raise TypeError("filename must be string type")

    cattrs = ffi.new("char[F_ATTR_ALL]")
    response = ffi.new("nvlist_t **")
    # ffi.gc return a new cdata object that points to the same data. Later,
    # when this new cdata object is garbage-collected, the destructor
    # (in this case 'lib.nvlist_free' will be called.
    response[0] = ffi.gc(response[0], lib.nvlist_free)
    bval = ffi.new("boolean_t *")
    pair = ffi.NULL
    next_pair = ffi.new("nvpair_t *")
    attr_list = []

    fd = os.open(filename, os.O_RDONLY)
    if fd == -1:
        raise OSError(ffi.errno, os.strerror(ffi.errno), filename)

    if lib.fgetattr(fd, lib.XATTR_VIEW_READWRITE, response):
        os.close(fd)
        raise OSError(ffi.errno, os.strerror(ffi.errno), filename)
    os.close(fd)

    count = 0
    pair = lib.nvlist_next_nvpair(response[0], pair)
    while pair != ffi.NULL:
        name = lib.nvpair_name(pair)
        next_pair = lib.nvlist_next_nvpair(response[0], pair)
        # we ignore all non-boolean attrs
        if lib.nvpair_type(pair) != lib.DATA_TYPE_BOOLEAN_VALUE:
            pair = next_pair
            continue

        if lib.nvpair_value_boolean_value(pair, bval) != 0:
            raise OSError("could not read attr value")

        if bval[0]:
            if compact:
                if count >= F_ATTR_ALL:
                    raise OSError("Too many system attributes found")
                cattrs[count] = lib.attr_to_option(lib.name_to_attr(name))[0]
                count += 1
            else:
                # ffi.string returns a bytes
                string = force_text(ffi.string(name))
                if string:
                    attr_list.append(string)
        pair = next_pair

    if compact:
        cattrs = force_text(ffi.string(cattrs))
        return cattrs
    return attr_list


def fsetattr(filename, attr):
    """Set system attributes for a file. The system attributes can either be
    passed as a list of verbose attribute names or a string that consists of
    a sequence of compact attribute options.

    Raises ValueError for invalid system attributes or OSError (with errno set)
    if any of the library calls fail.

    Input examples:
      verbose attributes example: ['hidden', 'archive', 'sensitive', ... ]

    compact attributes example: 'HAT'
    """

    from pkg.misc import force_bytes
    if not isinstance(filename, six.string_types):
        raise TypeError("filename must be string type")
    if not attr:
        raise TypeError("{0} is not a valid system attribute".format(attr))

    compact = False
    sys_attr = -1
    request = ffi.new("nvlist_t **")
    request[0] = ffi.gc(request[0], lib.nvlist_free)

    if lib.nvlist_alloc(request, lib.NV_UNIQUE_NAME, 0) != 0:
        raise OSError(ffi.errno, os.strerror(ffi.errno))

    # A single string indicates system attributes are passed in compact
    # form (e.g. AHi), verbose attributes are read as a list of strings.
    if isinstance(attr, six.string_types):
        compact = True

    for c in attr:
        c = force_bytes(c)
        if compact:
            sys_attr = lib.option_to_attr(c)
        else:
            sys_attr = lib.name_to_attr(c)

        if sys_attr == lib.F_ATTR_INVAL:
            if compact:
                raise ValueError("{0} is not a valid compact system "
                                 "attribute".format(attr))
            else:
                raise ValueError("{0} is not a valid verbose system "
                                 "attribute".format(attr))
        if not is_supported(sys_attr):
            if compact:
                raise ValueError("{0} is not a supported compact system "
                                 "attribute".format(attr))
            else:
                raise ValueError("{0} is not a supported verbose system "
                                 "attribute".format(attr))
        if lib.nvlist_add_boolean_value(request[0], lib.attr_to_name(sys_attr),
                                        1) != 0:
            raise OSError(ffi.errno, os.strerror(ffi.errno))

    fd = os.open(filename, os.O_RDONLY)
    if fd == -1:
        raise OSError(ffi.errno, os.strerror(ffi.errno), filename)

    if lib.fsetattr(fd, lib.XATTR_VIEW_READWRITE, request[0]):
        os.close(fd)
        raise OSError(ffi.errno, os.strerror(ffi.errno), filename)
    os.close(fd)


def get_attr_dict():
    """Get a dictionary containing all supported system attributes in the form:

        { <verbose_name>: <compact_option>,
          ...
        }
    """

    from pkg.misc import force_text
    sys_attrs = {}
    for i in range(F_ATTR_ALL):
        if not is_supported(i):
            continue
        key = force_text(ffi.string(lib.attr_to_name(i)))
        value = force_text(ffi.string(lib.attr_to_option(i)))
        sys_attrs.setdefault(key, value)
    return sys_attrs
