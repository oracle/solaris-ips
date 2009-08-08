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
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import os
import types
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
        def __init__(self, args, bufsize=128 * 1024, executable=None,
            stdin=None, stdout=None, stderr=None, preexec_fn=None,
            close_fds=False, shell=False, cwd=None, env=None,
            universal_newlines=False, startupinfo=None, creationflags=0):

                subprocess.Popen.__init__(self, args, bufsize, executable,
                    stdin, stdout, stderr, preexec_fn, close_fds, shell, cwd,
                    env, universal_newlines, startupinfo, creationflags)


        if "posix_spawnp" in globals():

                def _execute_child(self, args, executable, preexec_fn,
                    close_fds, cwd, env, universal_newlines, startupinfo,
                    creationflags, shell, p2cread, p2cwrite, c2pread, c2pwrite,
                    errread, errwrite):
                        """Execute program using posix spawn"""

                        if isinstance(args, types.StringTypes):
                                args = [args]

                        if shell:
                                args = ["/bin/sh", "-c"] + args

                        if executable == None:
                                executable = args[0]

                        sfa = SpawnFileAction()

                        # Child file actions
                        # Close parent's pipe ends
                        if p2cwrite:
                                sfa.add_close(p2cwrite)
                        if c2pread:
                                sfa.add_close(c2pread)
                        if errread:
                                sfa.add_close(errread)

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
                        if c2pwrite and c2pwrite not in (p2cread,):
                                sfa.add_close(c2pwrite)
                        if errwrite and errwrite not in (p2cread, c2pwrite):
                                sfa.add_close(errwrite)

                        # Close all other fds, if asked for.
                        if close_fds:
                                sfa.add_close_childfds()

                        if cwd != None:
                                os.chdir(cwd)

                        if preexec_fn:
                                apply(preexec_fn)

                        if not env:
                                # If caller didn't pass us an environment in
                                # env, borrow the env that the current process
                                # is using.
                                env = [ "%s=%s" % (k, v) for k, v in\
                                    os.environ.items() ]

                        self.pid = posix_spawnp(executable, args, sfa, env)

                        # Parent
                        if p2cread and p2cwrite:
                                os.close(p2cread)
                        if c2pwrite and c2pread:
                                os.close(c2pwrite)
                        if errwrite and errread:
                                os.close(errwrite)
