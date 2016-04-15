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
# Copyright (c) 2012, 2016, Oracle and/or its affiliates. All rights reserved.
#

"""
Interfaces used within the package client to operate on a remote image.
Primarily used by linked images when recursing into child images.
"""

# standard python classes
import os
import select
import six
import subprocess
import tempfile
import traceback

# pkg classes
import pkg.client.api_errors as apx
import pkg.client.pkgdefs as pkgdefs
import pkg.misc
import pkg.nrlock
import pkg.pipeutils

from pkg.client import global_settings
from pkg.client.debugvalues import DebugValues

# debugging aids
# DebugValues is a singleton; pylint: disable=E1120
pkgremote_debug = (
    DebugValues.get_value("pkgremote_debug") is not None or
    os.environ.get("PKG_PKGREMOTE_DEBUG", None) is not None)

class PkgRemote(object):
        """This class is used to perform packaging operation on an image.  It
        utilizes the "remote" subcommand within the pkg.1 client to manipulate
        images.  Communication between this class and the "pkg remote" process
        is done via RPC.  This class essentially implements an RPC client and
        the "pkg remote" process is an RPC server."""

        # variables to keep track of our RPC client call state.
        __IDLE     = "call-idle"
        __SETUP    = "call-setup"
        __STARTED  = "call-started"

        def __init__(self):
                # initialize RPC server process state
                self.__rpc_server_proc = None
                self.__rpc_server_fstdout = None
                self.__rpc_server_fstderr = None
                self.__rpc_server_prog_pipe_fobj = None

                # initialize RPC client process state
                self.__rpc_client = None
                self.__rpc_client_prog_pipe_fobj = None

                # initialize RPC client call state
                self.__state = self.__IDLE
                self.__pkg_op = None
                self.__kwargs = None
                self.__async_rpc_caller = None
                self.__async_rpc_waiter = None
                self.__result = None

                # sanity check the idle state by re-initializing it
                self.__set_state_idle()

        def __debug_msg(self, msg, t1=False, t2=False):
                """Log debugging messages."""

                if not pkgremote_debug:
                        return

                if t1:
                        prefix = "PkgRemote({0}) client thread 1: ".format(
                            id(self))
                elif t2:
                        prefix = "PkgRemote({0}) client thread 2: ".format(
                            id(self))
                else:
                        prefix = "PkgRemote({0}) client: ".format(id(self))

                # it's not an enforcement but a coding style
                # logging-format-interpolation; pylint: disable=W1202
                global_settings.logger.info("{0}{1}".format(prefix, msg))

        def __rpc_server_fork(self, img_path,
            server_cmd_pipe, server_prog_pipe_fobj):
                """Fork off a "pkg remote" server process.

                'img_path' is the path to the image to manipulate.

                'server_cmd_pipe' is the server side of the command pipe which
                the server will use to receive RPC requests.

                'server_prog_pipe_fobj' is the server side of the progress
                pipe which the server will write to to indicate progress."""

                pkg_cmd = pkg.misc.api_pkgcmd() + [
                    "-R", img_path,
                    "--runid={0}".format(global_settings.client_runid),
                    "remote",
                    "--ctlfd={0}".format(server_cmd_pipe),
                    "--progfd={0}".format(server_prog_pipe_fobj.fileno()),
                ]

                self.__debug_msg("RPC server cmd: {0}".format(
                    " ".join(pkg_cmd)))

                # create temporary files to log standard output and error from
                # the RPC server.
                fstdout = tempfile.TemporaryFile()
                fstderr = tempfile.TemporaryFile()

                try:
                        # Under Python 3.4, os.pipe() returns non-inheritable
                        # file descriptors. On UNIX, subprocess makes file
                        # descriptors of the pass_fds parameter inheritable.
                        # Since our pkgsubprocess use posix_pspawn* and doesn't
                        # have an interface for pass_fds, we reuse the Python
                        # module subprocess here.
                        # unexpected-keyword-arg 'pass_fds';
                        # pylint: disable=E1123
                        if six.PY2:
                                p = pkg.pkgsubprocess.Popen(pkg_cmd,
                                    stdout=fstdout, stderr=fstderr)
                        else:
                                p = subprocess.Popen(pkg_cmd,
                                    stdout=fstdout, stderr=fstderr,
                                    pass_fds=(server_cmd_pipe,
                                    server_prog_pipe_fobj.fileno()))

                except OSError as e:
                        # Access to protected member; pylint: disable=W0212
                        raise apx._convert_error(e)

                # initalization successful, update RPC server state
                self.__rpc_server_proc = p
                self.__rpc_server_fstdout = fstdout
                self.__rpc_server_fstderr = fstderr
                self.__rpc_server_prog_pipe_fobj = server_prog_pipe_fobj

        def __rpc_server_setup(self, img_path):
                """Start a new RPC Server process.

                'img_path' is the path to the image to manipulate."""

                # create a pipe for communication between the client and server
                client_cmd_pipe, server_cmd_pipe = os.pipe()
                # create a pipe that the server server can use to indicate
                # progress to the client.  wrap the pipe fds in python file
                # objects so that they gets closed automatically when those
                # objects are dereferenced.
                client_prog_pipe, server_prog_pipe = os.pipe()
                client_prog_pipe_fobj = os.fdopen(client_prog_pipe, "r")
                server_prog_pipe_fobj = os.fdopen(server_prog_pipe, "w")

                # initialize the client side of the RPC server
                rpc_client = pkg.pipeutils.PipedServerProxy(client_cmd_pipe)

                # fork off the server
                self.__rpc_server_fork(img_path,
                    server_cmd_pipe, server_prog_pipe_fobj)

                # close our reference to server end of the pipe.  (the server
                # should have already closed its reference to the client end
                # of the pipe.)
                os.close(server_cmd_pipe)

                # initalization successful, update RPC client state
                self.__rpc_client = rpc_client
                self.__rpc_client_prog_pipe_fobj = client_prog_pipe_fobj

        def __rpc_server_fini(self):
                """Close connection to a RPC Server process."""

                # destroying the RPC client object closes our connection to
                # the server, which should cause the server to exit.
                self.__rpc_client = None

                # if we have a server, kill it and wait for it to exit
                if self.__rpc_server_proc:
                        self.__rpc_server_proc.terminate()
                        self.__rpc_server_proc.wait()

                # clear server state (which closes the rpc pipe file
                # descriptors)
                self.__rpc_server_proc = None
                self.__rpc_server_fstdout = None
                self.__rpc_server_fstderr = None

                # wait for any client RPC threads to exit
                if self.__async_rpc_caller:
                        self.__async_rpc_caller.join()
                if self.__async_rpc_waiter:
                        self.__async_rpc_waiter.join()

                # close the progress pipe
                self.__rpc_server_prog_pipe_fobj = None
                self.__rpc_client_prog_pipe_fobj = None

        def fileno(self):
                """Return the progress pipe for the server process.  We use
                this to monitor progress in the RPC server"""

                return self.__rpc_client_prog_pipe_fobj.fileno()

        def __rpc_client_prog_pipe_drain(self):
                """Drain the client progress pipe."""

                progfd = self.__rpc_client_prog_pipe_fobj.fileno()
                p = select.poll()
                p.register(progfd, select.POLLIN)
                while p.poll(0):
                        os.read(progfd, 10240)

        def __state_verify(self, state=None):
                """Sanity check our internal call state.

                'state' is an optional parameter that indicates which state
                we should be in now.  (without this parameter we just verify
                that the current state, whatever it is, is self
                consistent.)"""

                if state is not None:
                        assert self.__state == state, \
                            "{0} == {1}".format(self.__state, state)
                else:
                        state = self.__state

                if state == self.__IDLE:
                        assert self.__pkg_op is None, \
                            "{0} is None".format(self.__pkg_op)
                        assert self.__kwargs is None, \
                            "{0} is None".format(self.__kwargs)
                        assert self.__async_rpc_caller is None, \
                            "{0} is None".format(self.__async_rpc_caller)
                        assert self.__async_rpc_waiter is None, \
                            "{0} is None".format(self.__async_rpc_waiter)
                        assert self.__result is None, \
                            "{0} is None".format(self.__result)

                elif state == self.__SETUP:
                        assert self.__pkg_op is not None, \
                            "{0} is not None".format(self.__pkg_op)
                        assert self.__kwargs is not None, \
                            "{0} is not None".format(self.__kwargs)
                        assert self.__async_rpc_caller is None, \
                            "{0} is None".format(self.__async_rpc_caller)
                        assert self.__async_rpc_waiter is None, \
                            "{0} is None".format(self.__async_rpc_waiter)
                        assert self.__result is None, \
                            "{0} is None".format(self.__result)

                elif state == self.__STARTED:
                        assert self.__pkg_op is not None, \
                            "{0} is not None".format(self.__pkg_op)
                        assert self.__kwargs is not None, \
                            "{0} is not None".format(self.__kwargs)
                        assert self.__async_rpc_caller is not None, \
                            "{0} is not None".format(self.__async_rpc_caller)
                        assert self.__async_rpc_waiter is not None, \
                            "{0} is not None".format(self.__async_rpc_waiter)
                        assert self.__result is None, \
                            "{0} is None".format(self.__result)

        def __set_state_idle(self):
                """Enter the __IDLE state.  This clears all RPC call
                state."""

                # verify the current state
                self.__state_verify()

                # setup the new state
                self.__state = self.__IDLE
                self.__pkg_op = None
                self.__kwargs = None
                self.__async_rpc_caller = None
                self.__async_rpc_waiter = None
                self.__result = None
                self.__debug_msg("set call state: {0}".format(self.__state))

                # verify the new state
                self.__state_verify()

        def __set_state_setup(self, pkg_op, kwargs):
                """Enter the __SETUP state.  This indicates that we're
                all ready to make a call into the RPC server.

                'pkg_op' is the packaging operation we're going to do via RPC

                'kwargs' is the argument dict for the RPC operation.

                't' is the RPC client thread that will call into the RPC
                server."""

                # verify the current state
                self.__state_verify(state=self.__IDLE)

                # setup the new state
                self.__state = self.__SETUP
                self.__pkg_op = pkg_op
                self.__kwargs = kwargs
                self.__debug_msg("set call state: {0}, pkg op: {1}".format(
                    self.__state, pkg_op))

                # verify the new state
                self.__state_verify()

        def __set_state_started(self, async_rpc_caller, async_rpc_waiter):
                """Enter the __SETUP state.  This indicates that we've
                started a call to the RPC server and we're now waiting for
                that call to return."""

                # verify the current state
                self.__state_verify(state=self.__SETUP)

                # setup the new state
                self.__state = self.__STARTED
                self.__async_rpc_caller = async_rpc_caller
                self.__async_rpc_waiter = async_rpc_waiter
                self.__debug_msg("set call state: {0}".format(self.__state))

                # verify the new state
                self.__state_verify()

        def __rpc_async_caller(self, fstdout, fstderr, rpc_client,
            pkg_op, **kwargs):
                """RPC thread callback.  This routine is invoked in its own
                thread (so the caller doesn't have to block) and it makes a
                blocking call to the RPC server.

                'kwargs' is the argument dict for the RPC operation."""

                self.__debug_msg("starting pkg op: {0}; args: {1}".format(
                    pkg_op, kwargs), t1=True)

                # make the RPC call
                rv = e = None
                rpc_method = getattr(rpc_client, pkg_op)
                try:
                        # Catch "Exception"; pylint: disable=W0703
                        rv = rpc_method(**kwargs)
                except Exception as e:
                        self.__debug_msg("caught exception\n{0}".format(
                            traceback.format_exc()), t1=True)
                else:
                        self.__debug_msg("returned: {0}".format(rv), t1=True)

                # get output generated by the RPC server.  the server
                # truncates its output file after each operation, so we always
                # read output from the beginning of the file.
                fstdout.seek(0)
                stdout = b"".join(fstdout.readlines())
                fstderr.seek(0)
                stderr = b"".join(fstderr.readlines())

                self.__debug_msg("exiting", t1=True)
                return (rv, e, stdout, stderr)

        def __rpc_async_waiter(self, async_call, prog_pipe):
                """RPC waiter thread.  This thread waits on the RPC thread
                and signals its completion by writing a byte to the progress
                pipe.

                The RPC call thread can't do this for itself because that
                results in a race (the RPC thread could block after writing
                this byte but before actually exiting, and then the client
                would read the byte, see that the RPC thread is not done, and
                block while trying to read another byte which would never show
                up).  This thread solves this problem without using any shared
                state."""

                self.__debug_msg("starting", t2=True)
                async_call.join()
                try:
                        os.write(prog_pipe.fileno(), b".")
                except (IOError, OSError):
                        pass
                self.__debug_msg("exiting", t2=True)

        def __rpc_client_setup(self, pkg_op, **kwargs):
                """Prepare to perform a RPC operation.

                'pkg_op' is the packaging operation we're going to do via RPC

                'kwargs' is the argument dict for the RPC operation."""

                self.__set_state_setup(pkg_op, kwargs)

                # drain the progress pipe
                self.__rpc_client_prog_pipe_drain()

        def setup(self, img_path, pkg_op, **kwargs):
                """Public interface to setup a remote packaging operation.

                'img_path' is the path to the image to manipulate.

                'pkg_op' is the packaging operation we're going to do via RPC

                'kwargs' is the argument dict for the RPC operation."""

                self.__debug_msg("setup()")
                self.__rpc_server_setup(img_path)
                self.__rpc_client_setup(pkg_op, **kwargs)

        def start(self):
                """Public interface to start a remote packaging operation."""

                self.__debug_msg("start()")
                self.__state_verify(self.__SETUP)

                async_rpc_caller = pkg.misc.AsyncCall()
                async_rpc_caller.start(
                     self.__rpc_async_caller,
                     self.__rpc_server_fstdout,
                     self.__rpc_server_fstderr,
                     self.__rpc_client,
                     self.__pkg_op,
                     **self.__kwargs)

                async_rpc_waiter = pkg.misc.AsyncCall()
                async_rpc_waiter.start(
                    self.__rpc_async_waiter,
                    async_rpc_caller,
                    self.__rpc_server_prog_pipe_fobj)

                self.__set_state_started(async_rpc_caller, async_rpc_waiter)

        def is_done(self):
                """Public interface to query if a remote packaging operation
                is done."""

                self.__debug_msg("is_done()")
                assert self.__state in [self.__SETUP, self.__STARTED]

                # drain the progress pipe.
                self.__rpc_client_prog_pipe_drain()

                if self.__state == self.__SETUP:
                        rv = False
                else:
                        # see if the client is done
                        rv = self.__async_rpc_caller.is_done()

                return rv

        def result(self):
                """Public interface to get the result of a remote packaging
                operation.  If the operation is not yet completed, this
                interface will block until it finishes.  The return value is a
                tuple which contains:

                'rv' is the return value of the RPC operation

                'e' is any exception generated by the RPC operation

                'stdout' is the standard output generated by the RPC server
                during the RPC operation.

                'stderr' is the standard output generated by the RPC server
                during the RPC operation."""

                self.__debug_msg("result()")
                self.__state_verify(self.__STARTED)

                rvtuple = e = None
                try:
                        rvtuple = self.__async_rpc_caller.result()
                except pkg.misc.AsyncCallException as ex:
                        # due to python 3 scoping rules
                        e = ex

                # assume we didn't get any results
                rv = pkgdefs.EXIT_OOPS
                stdout = stderr = ""

                # unpack our results if we got any
                if e is None:
                        # unpack our results.
                        # our results can contain an embedded exception.
                        # Attempting to unpack a non-sequence%s;
                        # pylint: disable=W0633
                        rv, e, stdout, stderr = rvtuple

                # make sure the return value is an int
                if type(rv) != int:
                        rv = pkgdefs.EXIT_OOPS

                # if we got any errors, make sure we return OOPS
                if e is not None:
                        rv = pkgdefs.EXIT_OOPS

                # shutdown the RPC server
                self.__rpc_server_fini()

                # pack up our results and enter the done state
                self.__set_state_idle()

                return (rv, e, stdout, stderr)

        def abort(self):
                """Public interface to abort an in-progress RPC operation."""

                assert self.__state in [self.__SETUP, self.__STARTED]

                self.__debug_msg("call abort requested")

                # shutdown the RPC server
                self.__rpc_server_fini()

                # enter the idle state
                self.__set_state_idle()
