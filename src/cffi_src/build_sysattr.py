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
# Copyright (c) 2015, 2023, Oracle and/or its affiliates.
#

from __future__ import unicode_literals
from cffi import FFI

ffi = FFI()

ffi.set_source("_sysattr", """
/* Includes */
#include <attr.h>
#include <errno.h>
#include <fcntl.h>
#include <stdbool.h>
#include <sys/nvpair.h>
""")

ffi.cdef("""
/* Macros */
#define	NV_UNIQUE_NAME 0x1

/* Types */
typedef enum {
    F_ATTR_INVAL = -1,
    F_ARCHIVE,
    F_HIDDEN,
    F_READONLY,
    F_SYSTEM,
    F_APPENDONLY,
    F_NODUMP,
    F_IMMUTABLE,
    F_AV_MODIFIED,
    F_OPAQUE,
    F_AV_SCANSTAMP,
    F_AV_QUARANTINED,
    F_NOUNLINK,
    F_CRTIME,
    F_OWNERSID,
    F_GROUPSID,
    F_FSID,
    F_REPARSE,
    F_GEN,
    F_OFFLINE,
    F_SPARSE,
    F_SENSITIVE,
    F_RETENTIONTIME,
    F_NORETAIN,
    F_ATTR_ALL
} f_attr_t;

typedef enum {
    DATA_TYPE_UNKNOWN = 0,
    DATA_TYPE_BOOLEAN,
    DATA_TYPE_BYTE,
    DATA_TYPE_INT16,
    DATA_TYPE_UINT16,
    DATA_TYPE_INT32,
    DATA_TYPE_UINT32,
    DATA_TYPE_INT64,
    DATA_TYPE_UINT64,
    DATA_TYPE_STRING,
    DATA_TYPE_BYTE_ARRAY,
    DATA_TYPE_INT16_ARRAY,
    DATA_TYPE_UINT16_ARRAY,
    DATA_TYPE_INT32_ARRAY,
    DATA_TYPE_UINT32_ARRAY,
    DATA_TYPE_INT64_ARRAY,
    DATA_TYPE_UINT64_ARRAY,
    DATA_TYPE_STRING_ARRAY,
    DATA_TYPE_HRTIME,
    DATA_TYPE_NVLIST,
    DATA_TYPE_NVLIST_ARRAY,
    DATA_TYPE_BOOLEAN_VALUE,
    DATA_TYPE_INT8,
    DATA_TYPE_UINT8,
    DATA_TYPE_BOOLEAN_ARRAY,
    DATA_TYPE_INT8_ARRAY,
    DATA_TYPE_UINT8_ARRAY,
    DATA_TYPE_DOUBLE
} data_type_t;

typedef enum {
    XATTR_VIEW_INVALID = -1,
    XATTR_VIEW_READONLY,
    XATTR_VIEW_READWRITE,
    XATTR_VIEW_LAST
} xattr_view_t;

typedef struct nvlist {
    int32_t     nvl_version;
    uint32_t    nvl_nvflag;     /* persistent flags */
    uint64_t    nvl_priv;       /* ptr to private data if not packed */
    uint32_t    nvl_flag;
    int32_t     nvl_pad;        /* currently not used, for alignment */
} nvlist_t;

typedef struct nvpair {
    /* name string */
    /* aligned ptr array for string arrays */
    /* aligned array of data for value */
    int32_t     nvp_size;       /* size of this nvpair */
    int16_t     nvp_name_sz;    /* length of name string */
    int16_t     nvp_reserve;    /* not used */
    int32_t     nvp_value_elem; /* number of elements for array types */
    data_type_t nvp_type;       /* type of value */
} nvpair_t;

typedef enum { _B_FALSE = 0, _B_TRUE = 1 } boolean_t;
typedef	unsigned int uint_t;

/* Functions */
const char *attr_to_name(f_attr_t);
const char *attr_to_option(f_attr_t);
f_attr_t name_to_attr(const char *name);
f_attr_t option_to_attr(const char *option);
int fgetattr(int, xattr_view_t, nvlist_t **);
int fsetattr(int, xattr_view_t, nvlist_t *);

int nvlist_alloc(nvlist_t **, uint_t, int);
void nvlist_free(nvlist_t *);
int nvlist_add_boolean_value(nvlist_t *, const char *, boolean_t);
nvpair_t *nvlist_next_nvpair(nvlist_t *, nvpair_t *);
char *nvpair_name(nvpair_t *);
data_type_t nvpair_type(nvpair_t *);
int nvpair_value_boolean_value(nvpair_t *, boolean_t *);
""")

if __name__ == "__main__":
    ffi.compile(tmpdir="./cffi_src")
