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
# Copyright (c) 2012, 2025, Oracle and/or its affiliates.
#

from . import testutils
if __name__ == "__main__":
    testutils.setup_environment("../../../proto")
import pkg5unittest

import multiprocessing
import os
import random
import signal
import sys
import threading
import time
import traceback

import pkg.nrlock
import pkg.pipeutils

from pkg.client.debugvalues import DebugValues
from pkg.misc import AsyncCall, AsyncCallException


class TestAsyncRPC(pkg5unittest.Pkg5TestCase):

    @staticmethod
    def __nop():
        pass

    @staticmethod
    def __add(x, y):
        return x + y

    @staticmethod
    def __raise_ex():
        raise Exception("raise_ex()")

    @staticmethod
    def __sleep(n):
        time.sleep(n)

    def test_async_basics(self):
        # test a simple async call with no parameters
        ac = AsyncCall()
        ac.start(self.__nop)
        ac.result()

        # test a simple async call with positional parameters
        ac = AsyncCall()
        ac.start(self.__add, 1, 2)
        rv = ac.result()
        self.assertEqual(rv, 3)

        # test a simple async call with keyword parameters
        ac = AsyncCall()
        ac.start(self.__add, x=1, y=2)
        rv = ac.result()
        self.assertEqual(rv, 3)

        # test async call with invalid arguments
        ac = AsyncCall()
        ac.start(self.__add, 1, 2, 3)
        self.assertRaisesRegex(AsyncCallException,
            "takes 2 positional arguments",
            ac.result)
        ac = AsyncCall()
        ac.start(self.__add, x=1, y=2, z=3)
        self.assertRaisesRegex(AsyncCallException,
            "got an unexpected keyword argument",
            ac.result)
        ac = AsyncCall()
        ac.start(self.__add, y=2, z=3)
        self.assertRaisesRegex(AsyncCallException,
            "got an unexpected keyword argument",
            ac.result)

    def test_async_thread_errors(self):
        # test exceptions raised in the AsyncCall class
        DebugValues["async_thread_error"] = 1
        ac = AsyncCall()
        ac.start(self.__nop)
        self.assertRaisesRegex(AsyncCallException,
            "async_thread_error",
            ac.result)

    def __server(self, client_pipefd, server_pipefd, http_enc=True):
        """Setup RPC Server."""

        os.close(client_pipefd)
        server = pkg.pipeutils.PipedRPCServer(server_pipefd,
            http_enc=http_enc)
        server.register_introspection_functions()
        server.register_function(self.__nop, "nop")
        server.register_function(self.__add, "add")
        server.register_function(self.__raise_ex, "raise_ex")
        server.register_function(self.__sleep, "sleep")
        server.serve_forever()

    def __server_setup(self, http_enc=True, use_proc=True):
        """Setup an rpc server."""

        # create a pipe to communicate between the client and server
        client_pipefd, server_pipefd = os.pipe()

        # check if the server should be a process or thread
        alloc_server = multiprocessing.Process
        if not use_proc:
            threading.Thread

        # fork off and start server process/thread
        server_proc = alloc_server(
            target=self.__server,
            args=(client_pipefd, server_pipefd),
            kwargs={ "http_enc": http_enc })
        server_proc.daemon = True
        server_proc.start()
        os.close(server_pipefd)

        # Setup ourselves as the client
        client_rpc = pkg.pipeutils.PipedServerProxy(client_pipefd,
            http_enc=http_enc)

        return (server_proc, client_rpc)

    def __server_setup_and_call(self, method, http_enc=True,
        use_proc=True, **kwargs):
        """Setup an rpc server and make a call to it.
        All calls are made asynchronously."""

        server_proc, client_rpc = self.__server_setup(
            http_enc=http_enc, use_proc=use_proc)
        method_cb = getattr(client_rpc, method)
        ac = AsyncCall()
        ac.start(method_cb, **kwargs)

        # Destroying all references to the client object should close
        # the client end of our pipe to the server, which in turn
        # should cause the server to cleanly exit.  If we hang waiting
        # for the server to exist then that's a bug.
        del method_cb, client_rpc

        try:
            rv = ac.result()
        except AsyncCallException as ex:
            # we explicitly delete the client rpc object to try and
            # ensure that any connection to the server process
            # gets closed (so that the server process exits).
            server_proc.join()
            raise

        server_proc.join()
        return rv

    def __test_rpc_basics(self, http_enc=True, use_proc=True):

        # our rpc server only support keyword parameters

        # test rpc call with no arguments
        rv = self.__server_setup_and_call("nop",
            http_enc=http_enc, use_proc=use_proc)
        self.assertEqual(rv, None)

        # test rpc call with two arguments
        rv = self.__server_setup_and_call("add", x=1, y=2,
            http_enc=http_enc, use_proc=use_proc)
        self.assertEqual(rv, 3)

        # test rpc call with an invalid number of arguments
        self.assertRaisesRegex(AsyncCallException,
            "Invalid parameters.",
            self.__server_setup_and_call,
            "add", x=1, y=2, z=3,
            http_enc=http_enc, use_proc=use_proc)

        # test rpc call of a non-existent method
        self.assertRaisesRegex(AsyncCallException,
            "Method foo not supported.",
            self.__server_setup_and_call,
            "foo",
            http_enc=http_enc, use_proc=use_proc)

        # test rpc call of a server function that raises an exception
        self.assertRaisesRegex(AsyncCallException,
            "Server error: .* Exception: raise_ex()",
            self.__server_setup_and_call,
            "raise_ex",
            http_enc=http_enc, use_proc=use_proc)

    def __test_rpc_interruptions(self, http_enc):

        # sanity check rpc sleep call
        rv = self.__server_setup_and_call("sleep", n=0,
            http_enc=http_enc)

        # test interrupted rpc calls by killing the server
        for i in range(10):
            server_proc, client_rpc = self.__server_setup(
                http_enc=http_enc)
            ac = AsyncCall()

            method = getattr(client_rpc, "sleep")
            ac.start(method, n=10000)
            del method, client_rpc

            # add optional one second delay so that we can try
            # kill before and after the call has been started.
            time.sleep(random.randint(0, 1))

            # vary how we kill the target
            if random.randint(0, 1) == 1:
                server_proc.terminate()
            else:
                os.kill(server_proc.pid, signal.SIGKILL)

            self.assertRaises(AsyncCallException, ac.result)
            server_proc.join()

    def test_rpc_basics(self):
        # tests rpc calls to another process
        self.__test_rpc_basics()
        self.__test_rpc_basics(http_enc=False)

        # tests rpc calls to another thread
        self.__test_rpc_basics(use_proc=False)
        self.__test_rpc_basics(http_enc=False, use_proc=False)

    def test_rpc_interruptions(self):
        self.__test_rpc_interruptions(http_enc=True)
        self.__test_rpc_interruptions(http_enc=False)
