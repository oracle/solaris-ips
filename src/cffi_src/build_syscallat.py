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

ffi.set_source("_syscallat", """
/* Includes */
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
""")

ffi.cdef("""
/* Types */
typedef	int... mode_t; /* file attribute type */

/* Functions */
int mkdirat(int, const char *, mode_t);
int openat(int, const char *, int, mode_t);
int renameat(int, const char *, int, const char *);
int unlinkat(int, const char *, int);
""")

if __name__ == "__main__":
    ffi.compile(tmpdir="./cffi_src")
