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
# Copyright (c) 2012, Oracle and/or its affiliates. All rights reserved.
#

"""
Interfaces to allow us to do RPC over pipes.

The following classes are implemented to allow pipes to be used in place of
file and socket objects:
        PipeFile
        PipeSocket

The following classes are implemented to allow HTTP client operations over a
pipe:
        PipedHTTPResponse
        PipedHTTPConnection
        PipedHTTP

The following classes are implemented to allow RPC servers operations
over a pipe:
        _PipedServer
        _PipedTransport
        _PipedHTTPRequestHandler
        _PipedRequestHandler
        PipedRPCServer

The following classes are implemented to allow RPC clients operations
over a pipe:
        PipedServerProxy

RPC clients should be prepared to catch the following exceptions:
        ProtocolError1
        ProtocolError2
        IOError

A RPC server can be implemented as follows:

        server = PipedRPCServer(server_pipe_fd)
        server.register_introspection_functions()
        server.register_function(lambda x,y: x+y, 'add')
        server.serve_forever()

A RPC client can be implemented as follows:

        client_rpc = PipedServerProxy(client_pipe_fd)
        print client_rpc.add(1, 2)
        del client_rpc
"""

import SocketServer
import errno
import fcntl
import httplib
import os
import socket
import stat
import struct
import sys
import tempfile
import threading
import traceback

# import JSON RPC libraries and objects
import jsonrpclib as rpclib
import jsonrpclib.jsonrpc as rpc
from jsonrpclib.SimpleJSONRPCServer import SimpleJSONRPCRequestHandler as \
    SimpleRPCRequestHandler
from jsonrpclib.SimpleJSONRPCServer import SimpleJSONRPCDispatcher as \
    SimpleRPCDispatcher

#
# These includes make it easier for clients to catch the specific
# exceptions that can be raised by this module.
#
# Unused import; pylint: disable=W0611
from jsonrpclib import ProtocolError as ProtocolError1
from xmlrpclib import ProtocolError as ProtocolError2
# Unused import; pylint: enable=W0611

# debugging
pipeutils_debug = (os.environ.get("PKG_PIPEUTILS_DEBUG", None) is not None)

class PipeFile(object):
        """Object which makes a pipe look like a "file" object.

        Note that all data transmitted via this pipe is transmitted
        indirectly.  Any data written to or read from the pipe is actually
        transmitted via temporary files.  For sending data, the data is
        written to a temporary file and then the associated file descriptor is
        sent via the pipe.  For receiving data we try to read a file
        descriptor from the pipe and when we get one we return the data from
        the temporary file associated with the file descriptor that we just
        read.  This is done to help ensure that processes don't block while
        writing to these pipes (otherwise consumers of these interfaces would
        have to create threads to constantly drain data from these pipes to
        prevent clients from blocking).

        This class also support additional non-file special operations like
        sendfd() and recvfd()."""

        def __init__(self, fd, debug_label, debug=pipeutils_debug):
                self.__pipefd = fd
                self.__readfh = None
                self.closed = False

                # Pipes related objects should never live past an exec
                flags = fcntl.fcntl(self.__pipefd, fcntl.F_GETFD)
                flags |= fcntl.FD_CLOEXEC
                fcntl.fcntl(self.__pipefd, fcntl.F_SETFD, flags)

                self.debug = debug
                self.debug_label = debug_label
                self.debug_msg("__init__")

        def __del__(self):
                self.debug_msg("__del__")
                if not self.closed:
                        self.close()

        def debug_msg(self, op, msg=None):
                """If debugging is enabled display msg."""
                if not self.debug:
                        return

                if msg is not None:
                        msg = ": %s" % msg
                else:
                        msg = ""

                if self.debug_label is not None:
                        label = "%s: %s" % (os.getpid(), self.debug_label)
                else:
                        label = "%s" % os.getpid()

                print >> sys.stderr, "%s: %s.%s(%d)%s" % \
                    (label, op, type(self).__name__, self.__pipefd, msg)

        def debug_dumpfd(self, op, fd):
                """If debugging is enabled dump the contents of fd."""
                if not self.debug:
                        return

                si = os.fstat(fd)
                if not stat.S_ISREG(si.st_mode):
                        msg = "fd=%d" % fd
                else:
                        os.lseek(fd, os.SEEK_SET, 0)
                        msg = "".join(os.fdopen(os.dup(fd)).readlines())
                        msg = "msg=%s" % (msg)
                        os.lseek(fd, os.SEEK_SET, 0)

                self.debug_msg(op, msg)

        def fileno(self):
                """Required to support select.select()."""
                return self.__pipefd

        def readline(self):
                """Read one entire line from the pipe.
                Can block waiting for input."""

                if self.__readfh is not None:
                        # read from the fd that we received over the pipe
                        data = self.__readfh.readline()
                        if data != "":
                                return data
                        # the fd we received over the pipe is empty
                        self.__readfh = None

                # recieve a file descriptor from the pipe
                fd = self.recvfd()
                if fd == -1:
                        return ""
                self.__readfh = os.fdopen(fd)
                # return data from the received fd
                return self.readline()

        def read(self, size=-1):
                """Read at most size bytes from the pipe.
                Can block waiting for input."""

                if self.__readfh is not None:
                        # read from the fd that we received over the pipe
                        data = self.__readfh.read(size)
                        if data != "":
                                return data
                        # the fd we received over the pipe is empty
                        self.__readfh = None

                # recieve a file descriptor from the pipe
                fd = self.recvfd()
                if fd == -1:
                        return ""
                self.__readfh = os.fdopen(fd)
                # return data from the received fd
                return self.read(size)

        def write(self, msg):
                """Write a string to the pipe."""
                mf = tempfile.TemporaryFile()
                mf.write(msg)
                mf.flush()
                self.sendfd(mf.fileno())
                mf.close()

        def close(self):
                """Close the pipe."""
                if self.closed:
                        return
                self.debug_msg("close")
                os.close(self.__pipefd)
                self.__readfh = None
                self.closed = True

        def flush(self):
                """A NOP since we never do any buffering of data."""
                pass

        def sendfd(self, fd):
                """Send a file descriptor via the pipe."""

                if self.closed:
                        self.debug_msg("sendfd", "failed (closed)")
                        raise IOError(
                            "sendfd() called for closed %s" %
                            type(self).__name__)

                self.debug_dumpfd("sendfd", fd)
                try:
                        fcntl.ioctl(self.__pipefd, fcntl.I_SENDFD, fd)
                except:
                        self.debug_msg("sendfd", "failed")
                        raise

        def recvfd(self):
                """Receive a file descriptor via the pipe."""

                if self.closed:
                        self.debug_msg("recvfd", "failed (closed)")
                        raise IOError(
                            "sendfd() called for closed %s" %
                            type(self).__name__)

                try:
                        fcntl_args = struct.pack('i', -1)
                        fcntl_rv = fcntl.ioctl(self.__pipefd,
                            fcntl.I_RECVFD, fcntl_args)
                        fd = struct.unpack('i', fcntl_rv)[0]
                except IOError, e:
                        if e.errno == errno.ENXIO:
                                # other end of the connection was closed
                                return -1
                        self.debug_msg("recvfd", "failed")
                        raise e
                assert fd != -1

                # debugging
                self.debug_dumpfd("recvfd", fd)

                # reset the current file pointer
                si = os.fstat(fd)
                if stat.S_ISREG(si.st_mode):
                        os.lseek(fd, os.SEEK_SET, 0)

                return fd


class PipeSocket(PipeFile):
        """Object which makes a pipe look like a "socket" object."""

        def __init__(self, fd, debug_label, debug=pipeutils_debug):
                PipeFile.__init__(self, fd, debug_label, debug=debug)

        def makefile(self, mode='r', bufsize=-1):
                """Return a file-like object associated with this pipe.
                The pipe will be duped for this new object so that the object
                can be closed and garbage-collected independently."""
                # Unused argument; pylint: disable=W0613

                dup_fd = os.dup(self.fileno())
                self.debug_msg("makefile", "dup fd=%d" % dup_fd)
                return PipeFile(dup_fd, self.debug_label, debug=self.debug)

        def recv(self, bufsize, flags=0):
                """Receive data from the pipe.
                Can block waiting for input."""
                # Unused argument; pylint: disable=W0613
                return self.read(bufsize)

        def send(self, msg, flags=0):
                """Send data to the Socket.
                Should never really block."""
                # Unused argument; pylint: disable=W0613
                return self.write(msg)

        def sendall(self, msg):
                """Send data to the pipe.
                Should never really block."""
                self.write(msg)

        @staticmethod
        def shutdown(how):
                """Nothing to do here.  Move along."""
                # Unused argument; pylint: disable=W0613
                return


class PipedHTTPResponse(httplib.HTTPResponse):
        """Create a httplib.HTTPResponse like object that can be used with
        a pipe as a transport.  We override the minimum number of parent
        routines necessary."""

        def begin(self):
                """Our connection will never be automatically closed, so set
                will_close to False."""

                httplib.HTTPResponse.begin(self)
                self.will_close = False
                return


class PipedHTTPConnection(httplib.HTTPConnection):
        """Create a httplib.HTTPConnection like object that can be used with
        a pipe as a transport.  We override the minimum number of parent
        routines necessary."""

        # we use PipedHTTPResponse in place of httplib.HTTPResponse
        response_class = PipedHTTPResponse

        def __init__(self, fd, port=None, strict=None):
                assert port is None

                # invoke parent constructor
                httplib.HTTPConnection.__init__(self, "localhost",
                    strict=strict)

                # self.sock was initialized by httplib.HTTPConnection
                # to point to a socket, overwrite it with a pipe.
                assert(type(fd) == int) and os.fstat(fd)
                self.sock = PipeSocket(fd, "client-connection")

        def __del__(self):
                # make sure the destructor gets called for our pipe
                if self.sock is not None:
                        self.close()

        def close(self):
                """Close our pipe fd."""
                self.sock.close()
                self.sock = None

        def fileno(self):
                """Required to support select()."""
                return self.sock.fileno()


class PipedHTTP(httplib.HTTP):
        """Create httplib.HTTP like object that can be used with
        a pipe as a transport.  We override the minimum number of parent
        routines necessary.

        xmlrpclib uses the legacy httplib.HTTP class interfaces (instead of
        the newer class httplib.HTTPConnection interfaces), so we need to
        provide a "Piped" compatibility class that wraps the httplib.HTTP
        compatibility class."""

        _connection_class = PipedHTTPConnection

        @property
        def sock(self):
                """Return the "socket" associated with this HTTP pipe
                connection."""
                return self._conn.sock


class _PipedTransport(rpc.Transport):
        """Create a Transport object which can create new PipedHTTP
        connections via an existing pipe."""

        def __init__(self, fd, http_enc=True):
                self.__pipe_file = PipeFile(fd, "client-transport")
                self.__http_enc = http_enc
                rpc.Transport.__init__(self)
                self.verbose = False

        def __del__(self):
                # make sure the destructor gets called for our connection
                if self.__pipe_file is not None:
                        self.close()

        def close(self):
                """Close the pipe associated with this transport."""
                self.__pipe_file.close()
                self.__pipe_file = None

        def make_connection(self, host):
                """Create a new PipedHTTP connection to the server.  This
                involves creating a new pipe, and sending one end of the pipe
                to the server, and then wrapping the local end of the pipe
                with a PipedHTTP object.  This object can then be subsequently
                used to issue http requests."""
                # Redefining name from outer scope; pylint: disable=W0621

                assert self.__pipe_file is not None

                client_pipefd, server_pipefd = os.pipe()
                self.__pipe_file.sendfd(server_pipefd)
                os.close(server_pipefd)

                if self.__http_enc:
                        # we're using http encapsulation so return a
                        # PipedHTTP connection object
                        return PipedHTTP(client_pipefd)

                # we're not using http encapsulation so return a
                # PipeSocket object
                return PipeSocket(client_pipefd, "client-connection")

        def request(self, host, handler, request_body, verbose=0):
                """Send a request to the server."""

                if self.__http_enc:
                        # we're using http encapsulation so just pass the
                        # request to our parent class.
                        return rpc.Transport.request(self,
                            host, handler, request_body, verbose)

                c = self.make_connection(host)
                c.send(request_body)
                return self._parse_response(c.makefile(), c)


class _PipedServer(SocketServer.BaseServer):
        """Modeled after SocketServer.TCPServer."""

        def __init__(self, fd, RequestHandlerClass):
                self.__pipe_file = PipeFile(fd, "server-transport")
                self.__shutdown_initiated = False

                SocketServer.BaseServer.__init__(self,
                    server_address="localhost",
                    RequestHandlerClass=RequestHandlerClass)

        def fileno(self):
                """Required to support select.select()."""
                return self.__pipe_file.fileno()

        def initiate_shutdown(self):
                """Trigger a shutdown of the RPC server.  This is done via a
                separate thread since the shutdown() entry point is
                non-reentrant."""

                if self.__shutdown_initiated:
                        return
                self.__shutdown_initiated = True

                def shutdown_self(server_obj):
                        """Shutdown the server thread."""
                        server_obj.shutdown()

                t = threading.Thread(
                    target=shutdown_self, args=(self,))
                t.start()

        def get_request(self):
                """Get a request from the client.  Returns a tuple containing
                the request and the client address (mirroring the return value
                from self.socket.accept())."""

                fd = self.__pipe_file.recvfd()
                if fd == -1:
                        self.initiate_shutdown()
                        raise socket.error()

                return (PipeSocket(fd, "server-connection"),
                    ("localhost", None))


class _PipedHTTPRequestHandler(SimpleRPCRequestHandler):
        """Piped RPC request handler that uses HTTP encapsulation."""

        def setup(self):
                """Prepare to handle a request."""

                rv = SimpleRPCRequestHandler.setup(self)

                # StreamRequestHandler will have duped our PipeSocket via
                # makefile(), so close the connection socket here.
                self.connection.close()
                return rv


class _PipedRequestHandler(_PipedHTTPRequestHandler):
        """Piped RPC request handler that doesn't use HTTP encapsulation."""

        def handle_one_request(self):
                """Handle one client request."""

                request = self.rfile.readline()
                response = ""
                try:
                        # Access to protected member; pylint: disable=W0212
                        response = self.server._marshaled_dispatch(request)
                # No exception type specified; pylint: disable=W0702
                except:
                        # The server had an unexpected exception.
                        # dump the error to stderr
                        print >> sys.stderr, traceback.format_exc()

                        # Return the error to the caller.
                        err_lines = traceback.format_exc().splitlines()
                        trace_string = '%s | %s' % \
                            (err_lines[-3], err_lines[-1])
                        fault = rpclib.Fault(-32603,
                            'Server error: %s' % trace_string)
                        response = fault.response()

                        # tell the server to exit
                        self.server.initiate_shutdown()

                self.wfile.write(response)
                self.wfile.flush()


class PipedRPCServer(_PipedServer, SimpleRPCDispatcher):
        """Modeled after SimpleRPCServer.  Differs in that
        SimpleRPCServer is derived from SocketServer.TCPServer but we're
        derived from _PipedServer."""

        def __init__(self, addr,
            logRequests=False, encoding=None, http_enc=True):

                self.logRequests = logRequests
                SimpleRPCDispatcher.__init__(self, encoding)

                requestHandler = _PipedHTTPRequestHandler
                if not http_enc:
                        requestHandler = _PipedRequestHandler

                _PipedServer.__init__(self, addr, requestHandler)

        def  __check_for_server_errors(self, response):
                """Check if a response is actually a fault object.  If so
                then it's time to die."""

                if type(response) != rpclib.Fault:
                        return

                # server encountered an error, time for seppuku
                self.initiate_shutdown()

        def _dispatch(self, *args, **kwargs):
                """Check for unexpected server exceptions while handling a
                request."""
                # pylint: disable=W0221
                # Arguments differ from overridden method;

                response = SimpleRPCDispatcher._dispatch(
                    self, *args, **kwargs)
                self.__check_for_server_errors(response)
                return response

        def _marshaled_single_dispatch(self, *args, **kwargs):
                """Check for unexpected server exceptions while handling a
                request."""
                # pylint: disable=W0221
                # Arguments differ from overridden method;

                response = SimpleRPCDispatcher._marshaled_single_dispatch(
                    self, *args, **kwargs)
                self.__check_for_server_errors(response)
                return response

        def _marshaled_dispatch(self, *args, **kwargs):
                """Check for unexpected server exceptions while handling a
                request."""
                # pylint: disable=W0221
                # Arguments differ from overridden method;

                response = SimpleRPCDispatcher._marshaled_dispatch(
                    self, *args, **kwargs)
                self.__check_for_server_errors(response)
                return response


class PipedServerProxy(rpc.ServerProxy):
        """Create a ServerProxy object that can be used to make calls to
        an RPC server on the other end of a pipe."""

        def __init__(self, pipefd, encoding=None, verbose=0, version=None,
            http_enc=True):
                self.__piped_transport = _PipedTransport(pipefd,
                    http_enc=http_enc)
                rpc.ServerProxy.__init__(self,
                    "http://localhost/RPC2",
                    transport=self.__piped_transport,
                    encoding=encoding, verbose=verbose, version=version)
