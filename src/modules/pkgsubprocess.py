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
# Copyright (c) 2008, 2016, Oracle and/or its affiliates. All rights reserved.
#

import os
import types
import six
import subprocess
import pkg.portable
try:
        import pkg.pspawn
        from pkg.pspawn import posix_spawnp
        from pkg.pspawn import SpawnFileAction
except ImportError:
        pass

__all__ = ["Popen", "PIPE", "STDOUT", "call"]

def call(*args, **kwargs):
        return Popen(*args, **kwargs).wait()

PIPE = subprocess.PIPE
STDOUT = subprocess.STDOUT

class Popen(subprocess.Popen):
        def __init__(self, args, pass_fds=None, **kwargs):
                if "bufsize" not in kwargs:
                        kwargs["bufsize"] = 128 * 1024
                subprocess.Popen.__init__(self, args, **kwargs)

        if "posix_spawnp" in globals():
                if six.PY2:
                        def _execute_child(self, args, executable, preexec_fn,
                            close_fds, cwd, env, universal_newlines, startupinfo,
                            creationflags, shell, to_close, p2cread, p2cwrite,
                            c2pread, c2pwrite, errread, errwrite):
                                """Execute program using posix spawn"""

                                if isinstance(args, (str, bytes)):
                                        args = [args]

                                if shell:
                                        args = ["/bin/sh", "-c"] + args

                                if executable == None:
                                        executable = args[0]

                                sfa = SpawnFileAction()

                                # Child file actions
                                # Close parent's pipe ends
                                closed_fds = []
                                if p2cwrite:
                                        sfa.add_close(p2cwrite)
                                        closed_fds.append(p2cwrite)
                                if c2pread:
                                        sfa.add_close(c2pread)
                                        closed_fds.append(c2pread)
                                if errread:
                                        sfa.add_close(errread)
                                        closed_fds.append(errread)

                                # When duping fds, if there arises a situation
                                # where one of the fds is either 0, 1 or 2, it
                                # is possible that it is overwritten (#12607).
                                if c2pwrite == 0:
                                        c2pwrite = os.dup(c2pwrite)
                                if errwrite == 0 or errwrite == 1:
                                        errwrite = os.dup(errwrite)

                                # Dup fds for child
                                if p2cread:
                                        sfa.add_dup2(p2cread, 0)
                                if c2pwrite:
                                        sfa.add_dup2(c2pwrite, 1)
                                if errwrite:
                                        sfa.add_dup2(errwrite, 2)

                                # Close pipe fds.  Make sure we don't close the
                                # same fd more than once.
                                if p2cread:
                                        sfa.add_close(p2cread)
                                        closed_fds.append(p2cread)
                                if c2pwrite and c2pwrite not in (p2cread,):
                                        sfa.add_close(c2pwrite)
                                        closed_fds.append(c2pwrite)
                                if errwrite and errwrite not in (p2cread, c2pwrite):
                                        sfa.add_close(errwrite)
                                        closed_fds.append(errwrite)

                                if cwd != None:
                                        os.chdir(cwd)

                                if preexec_fn:
                                        preexec_fn()

                                # Close all other fds, if asked for - after
                                # preexec_fn(), which may open FDs.
                                if close_fds:
                                #
                                # This is a bit tricky.  Due to a sad
                                # behaviour with posix_spawn in nevada
                                # builds before the fix for 6807216 (in
                                # nevada 110), (and perhaps on other OS's?)
                                # you can't have two close actions close the
                                # same FD, or an error results.  So we track
                                # everything we have closed, then manually
                                # fstat and close up to the max we have
                                # closed) .  Then we close everything above
                                # that efficiently with add_close_childfds().
                                #
                                        for i in range(3, max(closed_fds) + 1):
                                                # scheduled closed already? skip
                                                if i in closed_fds:
                                                        continue
                                                try:
                                                        os.fstat(i)
                                                        sfa.add_close(i)
                                                        closed_fds.append(i)
                                                except OSError:
                                                        pass
                                        closefrom = max([3, max(closed_fds) + 1])
                                        sfa.add_close_childfds(closefrom)

                                if env is None:
                                        # If caller didn't pass us an environment in
                                        # env, borrow the env that the current process
                                        # is using.
                                        env = os.environ.copy()

                                if type(env) == dict:
                                        # The bundled subprocess module takes a dict in
                                        # the "env" argument.  Allow that here by doing
                                        # the explicit conversion to a list.
                                        env = [
                                            "{0}={1}".format(k, v)
                                            for k, v in six.iteritems(env)
                                        ]

                                self.pid = posix_spawnp(executable, args, sfa, env)

                                self._child_created = True

                                if to_close:
                                        def _close_in_parent(fd):
                                                os.close(fd)
                                                to_close.remove(fd)
                                else:
                                        def _close_in_parent(fd):
                                                os.close(fd)

                                # Parent
                                if p2cread and p2cwrite:
                                        _close_in_parent(p2cread)
                                if c2pwrite and c2pread:
                                        _close_in_parent(c2pwrite)
                                if errwrite and errread:
                                        _close_in_parent(errwrite)
                else:
                        def _execute_child(self, args, executable, preexec_fn,
                            close_fds,
                            pass_fds, cwd, env,
                            startupinfo, creationflags, shell,
                            p2cread, p2cwrite,
                            c2pread, c2pwrite,
                            errread, errwrite,
                            restore_signals, start_new_session):
                                if isinstance(args, (str, bytes)):
                                        args = [args]

                                if shell:
                                        args = ["/bin/sh", "-c"] + args

                                if executable is None:
                                        executable = args[0]

                                sfa = SpawnFileAction()

                                # Child file actions
                                # Close parent's pipe ends
                                closed_fds = []
                                if p2cwrite != -1:
                                        sfa.add_close(p2cwrite)
                                        closed_fds.append(p2cwrite)
                                if c2pread != -1:
                                        sfa.add_close(c2pread)
                                        closed_fds.append(c2pread)
                                if errread != -1:
                                        sfa.add_close(errread)
                                        closed_fds.append(errread)

                                # Dup fds for child
                                if p2cread != -1:
                                        sfa.add_dup2(p2cread, 0)
                                if c2pwrite != -1:
                                        sfa.add_dup2(c2pwrite, 1)
                                if errwrite != -1:
                                        sfa.add_dup2(errwrite, 2)

                                # Close pipe fds.  Make sure we don't close the
                                # same fd more than once, or standard fds.
                                for fd in [p2cread, c2pwrite, errwrite]:
                                        if fd > 2 and fd not in closed_fds:
                                            sfa.add_close(fd)
                                            closed_fds.append(fd)

                                if cwd is not None:
                                        os.chdir(cwd)

                                if preexec_fn:
                                        preexec_fn()

                                # Close all other fds, if asked for - after
                                # preexec_fn(), which may open FDs.
                                if close_fds:
                                #
                                # This is a bit tricky.  Due to a sad
                                # behaviour with posix_spawn in nevada
                                # builds before the fix for 6807216 (in
                                # nevada 110), (and perhaps on other OS's?)
                                # you can't have two close actions close the
                                # same FD, or an error results.  So we track
                                # everything we have closed, then manually
                                # fstat and close up to the max we have
                                # closed) .  Then we close everything above
                                # that efficiently with add_close_childfds().
                                #
                                        # max() can't call on empty list, use a
                                        # trick "close_fds or [0]" to return 0
                                        # when closed_fds is empty.
                                        for i in range(3, max(closed_fds or [0]) + 1):
                                                # scheduled closed already? skip
                                                if i in closed_fds:
                                                        continue
                                                try:
                                                        os.fstat(i)
                                                        sfa.add_close(i)
                                                        closed_fds.append(i)
                                                except OSError:
                                                        pass
                                        closefrom = max([3, max(closed_fds or [0]) + 1])
                                        sfa.add_close_childfds(closefrom)

                                if env is None:
                                        # If caller didn't pass us an environment in
                                        # env, borrow the env that the current process
                                        # is using.
                                        env = os.environ.copy()

                                if type(env) == dict:
                                        # The bundled subprocess module takes a dict in
                                        # the "env" argument.  Allow that here by doing
                                        # the explicit conversion to a list.
                                        env = [
                                            "{0}={1}".format(k, v)
                                            for k, v in six.iteritems(env)
                                        ]

                                self.pid = posix_spawnp(executable, args, sfa,
                                    env)
                                self._child_created = True

                                # parent
                                devnull_fd = getattr(self, "_devnull", None)
                                if p2cread != -1 and p2cwrite != -1 and \
                                    p2cread != devnull_fd:
                                        os.close(p2cread)
                                if c2pwrite != -1 and c2pread != -1 and \
                                    c2pwrite != devnull_fd:
                                        os.close(c2pwrite)
                                if errwrite != -1 and errread != -1 and \
                                    errwrite != devnull_fd:
                                        os.close(errwrite)
                                if devnull_fd is not None:
                                        os.close(devnull_fd)
