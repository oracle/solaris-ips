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
from pkg._pspawn import lib, ffi


def _check_error(rc):
    if rc != 0:
        raise OSError(rc, os.strerror(rc))


@ffi.callback("int (*)(void *, int)", error=-1)
def walk_func(data, fd):
    wd = ffi.cast("walk_data *", data)
    if fd >= wd.start_fd and fd != wd.skip_fd:
        rc = lib.posix_spawn_file_actions_addclose(wd.fap, fd)
        _check_error(rc)
    return 0


class SpawnFileAction(object):

    """SpawnFileAction() -> spawn file action object

    Creates a Python object that encapsulates the posix_spawn_file_action_t
    type.  This is used by the posix_spawn(3C) interface to control actions
    on file descriptors in the new process.  This object implements the
    following methods.

    add_close(fd) -- Add the file descriptor fd to the list of fds to be
      closed in the new process.
    add_open(fd, path, oflag, mode) -- Open the file at path with flags
      oflags and mode, assign it to the file descriptor numbered fd in the new
      process.
    add_dup2(fd, newfd) -- Take the file descriptor in fd and dup2 it to newfd
      in the newly created process.
    add_close_childfds(fd) -- Add all file descriptors above 2 except fd
    (optionally) to list of fds to be closed in the new process.

    Information about the underlying C interfaces can be found in the
    following man pages:

    posix_spawn(3C)
    posix_spawn_file_actions_addclose(3C)
    posix_spawn_file_actions_addopen(3C)
    posix_spawn_file_actions_adddup2(3C)
    """

    def __init__(self):
        self.fa = ffi.new("posix_spawn_file_actions_t *")
        rc = lib.posix_spawn_file_actions_init(self.fa)
        self.fa = ffi.gc(self.fa, lib.posix_spawn_file_actions_destroy)
        # The file_actions routines don't set errno, so we have to create
        # the exception tuple by hand.
        _check_error(rc)

    def add_close(self, fd):
        """Add the file descriptor fd to the list of descriptors to be closed in
        the new process."""

        if not isinstance(fd, int):
            raise TypeError("fd must be int type")

        rc = lib.posix_spawn_file_actions_addclose(self.fa, fd)
        _check_error(rc)

    def add_open(self, fd, path, oflag, mode):
        """Open the file at path with flags oflags and mode, assign it to
        the file descriptor numbered fd in the new process."""

        if not isinstance(fd, int):
            raise TypeError("fd must be int type")
        if not isinstance(path, six.string_types):
            raise TypeError("path must be a string")
        if not isinstance(oflag, int):
            raise TypeError("oflag must be int type")
        if not isinstance(path, mode):
            raise TypeError("path must be int type")

        rc = lib.posix_spawn_file_actions_addopen(self.fa, fd, path, oflag,
                                                  mode)
        _check_error(rc)

    def add_dup2(self, fd, newfd):
        """Take the file descriptor in fd and dup2 it to newfd in the newly
        created process."""

        if not isinstance(fd, int):
            raise TypeError("fd must be int type")
        if not isinstance(newfd, int):
            raise TypeError("newfd must be int type")

        rc = lib.posix_spawn_file_actions_adddup2(self.fa, fd, newfd)
        _check_error(rc)

    def add_close_childfds(self, start_fd, except_fd=-1):
        """Add to a SpawnFileAction a series of 'closes' that will close all of
        the fds >= startfd in the child process.  A single fd may be skipped,
        provided that it is given as the optional except argument."""

        if not isinstance(start_fd, int):
            raise TypeError("start_fd must be int type")
        if not isinstance(except_fd, int):
            raise TypeError("except_fd must be int type")

        # Set up walk_data for fdwalk.
        wd = ffi.new("walk_data *", [0])
        wd.skip_fd = ffi.cast("int", except_fd)
        wd.start_fd = ffi.cast("int", start_fd)
        wd.fap = self.fa

        # Perform the walk.
        lib.fdwalk(walk_func, wd)


def posix_spawnp(filename, args, fileactions=None, env=None):
    """Invoke posix_spawnp(3C).

    'filename' is the name of the executeable file.

    'args' is a sequence of arguments supplied to the newly executed program.

    'fileactions' defines what actions will be performed upon the file
    descriptors of the spawned executable. If defined, it must be a
    SpawnFileAction object.

    'env', the enviroment, if provided, it must be a sequence object."""

    if not isinstance(filename, six.string_types):
        raise TypeError("filename must be a string")

    pid = ffi.new("pid_t *")

    spawn_args = [ffi.new("char []", arg) for arg in args]
    spawn_args.append(ffi.NULL)

    # Process env, if supplied by caller
    spawn_env = []
    if env:
        spawn_env = [ffi.new("char []", arg) for arg in env]
    spawn_env.append(ffi.NULL)

    # setup file actions, if passed by caller
    s_action = ffi.NULL
    if fileactions:
        if not isinstance(fileactions, SpawnFileAction):
            raise TypeError("fileact must be a SpawnFileAction object.")
        s_action = fileactions.fa

    # Now do the actual spawn
    rc = lib.posix_spawnp(pid, filename, s_action, ffi.NULL, spawn_args,
                          spawn_env)
    _check_error(rc)

    return pid[0]
