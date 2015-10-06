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
from cffi import FFI

ffi = FFI()

ffi.set_source("_arch", """
/* Includes */
#include <sys/systeminfo.h>
#include <stdlib.h>
""")

ffi.cdef("""
/* Macros */
#define	SI_RELEASE  3            /* return release of operating system */
#define	SI_ARCHITECTURE_32  516  /* basic 32-bit SI_ARCHITECTURE */
#define	SI_ARCHITECTURE_64  517  /* basic 64-bit SI_ARCHITECTURE */
#define	SI_PLATFORM 513          /* return platform identifier */

/* Functions */
void *malloc(size_t);
void *realloc(void *, size_t);
void free(void *);
int sysinfo(int, char *, long);
""")

if __name__ == "__main__":
    ffi.compile(tmpdir="./cffi_src")
