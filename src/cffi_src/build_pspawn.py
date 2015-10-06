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

ffi.set_source("_pspawn", """
/* Includes */
#include <spawn.h>
#include <sys/types.h>

/* Custom Types */
typedef struct {
    int skip_fd;
    int start_fd;
    posix_spawn_file_actions_t *fap;
} walk_data;
""")

ffi.cdef("""
/* Types */
typedef	int... mode_t;  /* file attribute type */
typedef int... pid_t;   /* process id type */

typedef struct {
    void *__file_attrp; /* implementation-private */
} posix_spawn_file_actions_t;

typedef struct {
    void *__spawn_attrp;    /* implementation-private */
} posix_spawnattr_t;

typedef struct {
    int skip_fd;
    int start_fd;
    posix_spawn_file_actions_t *fap;
} walk_data;

/* Functions */
int fdwalk(int (*)(void *, int), void *);
int posix_spawn_file_actions_init(posix_spawn_file_actions_t *);
int posix_spawn_file_actions_destroy(posix_spawn_file_actions_t *);
int posix_spawn_file_actions_addclose(posix_spawn_file_actions_t *, int);
int posix_spawn_file_actions_adddup2(posix_spawn_file_actions_t *, int, int);
int posix_spawn_file_actions_addopen(posix_spawn_file_actions_t *, int,
    const char *, int, mode_t);

int posix_spawnp(
    pid_t *,
    const char *,
    const posix_spawn_file_actions_t *,
    const posix_spawnattr_t *,
    char *const [],
    char *const []);
""")

if __name__ == "__main__":
    ffi.compile(tmpdir="./cffi_src")
