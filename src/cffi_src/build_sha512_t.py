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
# Copyright (c) 2015, 2024, Oracle and/or its affiliates.
#

from cffi import FFI

ffi = FFI()

ffi.set_source("_sha512_t", """
/* Includes */
#include <sys/sha2.h>
#include <string.h>
""")

ffi.cdef("""
/* Types */
typedef struct _sha2_ctx {
    uint16_t bitlength;     /* Digest Length in bits */
    uint16_t blocksize;     /* HMAC Block Size */
    union {
        uint32_t s32[8];
        uint64_t s64[8];
    } state;
    union {
        uint32_t c32[2];
        uint64_t c64[2];
    } count;
    union {
        uint8_t buf8[128];
        uint32_t buf32[16];
        uint64_t buf64[16];
    } buf_un;
} SHA512_CTX;

/* Functions */
void SHA512_t_Init(uint64_t t_bits, SHA512_CTX *ctx);
void SHA512_t_Update(SHA512_CTX *ctx, const void *buf, size_t bufsz);
void SHA512_t_Final(void *digest, SHA512_CTX *ctx);
void *memcpy(void *restrict s1, const void *restrict s2, size_t n);
""")

if __name__ == "__main__":
    ffi.compile(tmpdir="./cffi_src")
