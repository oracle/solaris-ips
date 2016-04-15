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
# Copyright (c) 2010, 2016, Oracle and/or its affiliates. All rights reserved.
#

from __future__ import print_function
import uuid as uuidm
import pkg.client.transport.exception as tx

from pkg.misc import DummyLock, force_str

class StreamingFileObj(object):

        def __init__(self, url, engine, ccancel=None):
                """Create a streaming file object that wraps around a
                transport engine.  This is only necessary if the underlying
                transport doesn't have its own streaming interface and the
                repo operation needs a streaming response."""

                self.__buf = b""
                self.__url = url
                self.__engine = engine
                self.__data_callback_invoked = False
                self.__headers_arrived = False
                self.__httpmsg = None
                self.__headers = {}
                self.__done = False
                self.__check_cancelation = ccancel
                self.__lock = DummyLock()
                self.__uuid = uuidm.uuid4().int
                # Free buffer on exception.  Set to False if caller may
                # read buffer after exception.  Caller should call close()
                # to cleanup afterwards.
                self.free_buffer = True

        def __del__(self):
                release = False
                try:
                        if not self.__done:
                                if not self.__lock._is_owned():
                                        self.__lock.acquire()
                                        release = True
                                self.__engine.orphaned_request(self.__url,
                                    self.__uuid)
                except AttributeError:
                        # Ignore attribute error if instance is deleted
                        # before initialization completes.
                        pass
                finally:
                        if release:
                                self.__lock.release()

        # File object methods

        def close(self):
                # Caller shouldn't hold lock when calling this method
                assert not self.__lock._is_owned()

                if not self.__done:
                        self.__lock.acquire()
                        try:
                                self.__engine.remove_request(self.__url,
                                    self.__uuid)
                                self.__done = True
                        finally:
                                self.__lock.release()
                self.__buf = b""
                self.__engine = None
                self.__url = None

        def flush(self):
                """flush the buffer.  Since this supports read, but
                not write, this is a noop."""
                return

        def read(self, size=-1):
                """Read size bytes from the remote connection.
                If size isn't specified, read all of the data from
                the remote side."""

                # Caller shouldn't hold lock when calling this method
                assert not self.__lock._is_owned()

                if size < 0:
                        while self.__fill_buffer():
                                # just fill the buffer
                                pass
                        curdata = self.__buf
                        self.__buf = b""
                        return curdata
                else:
                        curdata = self.__buf
                        datalen = len(curdata)
                        if datalen >= size:
                                self.__buf = curdata[size:]
                                return curdata[:size]
                        while self.__fill_buffer():
                                datalen = len(self.__buf)
                                if datalen >= size:
                                        break

                        curdata = self.__buf
                        datalen = len(curdata)
                        if datalen >= size:
                                self.__buf = curdata[size:]
                                return curdata[:size]

                        self.__buf = b""
                        return curdata

        def readline(self, size=-1):
                """Read a line from the remote host.  If size is
                specified, read to newline or size, whichever is smaller.
                We force the return value to be str here since the caller
                expect str."""

                # Caller shouldn't hold lock when calling this method
                assert not self.__lock._is_owned()

                if size < 0:
                        curdata = self.__buf
                        newline = curdata.find(b"\n")
                        if newline >= 0:
                                newline += 1
                                self.__buf = curdata[newline:]
                                return force_str(curdata[:newline])
                        while self.__fill_buffer():
                                newline = self.__buf.find(b"\n")
                                if newline >= 0:
                                        break

                        curdata = self.__buf
                        newline = curdata.find(b"\n")
                        if newline >= 0:
                                newline += 1
                                self.__buf = curdata[newline:]
                                return force_str(curdata[:newline])
                        self.__buf = b""
                        return force_str(curdata)
                else:
                        curdata = self.__buf
                        newline = curdata.find(b"\n", 0, size)
                        datalen = len(curdata)
                        if newline >= 0:
                                newline += 1
                                self.__buf = curdata[newline:]
                                return force_str(curdata[:newline])
                        if datalen >= size:
                                self.__buf = curdata[size:]
                                return force_str(curdata[:size])
                        while self.__fill_buffer():
                                newline = self.__buf.find(b"\n", 0, size)
                                datalen = len(self.__buf)
                                if newline >= 0:
                                        break
                                if datalen >= size:
                                        break

                        curdata = self.__buf
                        newline = curdata.find(b"\n", 0, size)
                        datalen = len(curdata)
                        if newline >= 0:
                                newline += 1
                                self.__buf = curdata[newline:]
                                return force_str(curdata[:newline])
                        if datalen >= size:
                                self.__buf = curdata[size:]
                                return force_str(curdata[:size])
                        self.__buf = b""
                        return force_str(curdata)

        def readlines(self, sizehint=0):
                """Read lines from the remote host, returning an
                array of the lines that were read.  sizehint specifies
                an approximate size, in bytes, of the total amount of data,
                as lines, that should be returned to the caller."""

                # Caller shouldn't hold lock when calling this method
                assert not self.__lock._is_owned()

                read = 0
                lines = []
                while True:
                        l = self.readline()
                        if not l:
                                break
                        lines.append(l)
                        read += len(l)
                        if sizehint and read >= sizehint:
                                break

                return lines

        def write(self, data):
                raise NotImplementedError

        def writelines(self, llist):
                raise NotImplementedError

        # Methods that access the callbacks

        def get_write_func(self):
                return self.__write_callback

        def get_header_func(self):
                return self.__header_callback

        def get_progress_func(self):
                return self.__progress_callback

        # Miscellaneous accessors

        def set_lock(self, lock):
                self.__lock = lock

        @property
        def uuid(self):
                return self.__uuid

        # Header and message methods

        def get_http_message(self):
                """Return the status message that may be included
                with a numerical HTTP response code.  Not all HTTP
                implementations are guaranteed to return this value.
                In some cases it may be None."""

                return self.__httpmsg

        def getheader(self, hdr, default):
                """Return the HTTP header named hdr.  If the hdr
                isn't present, return default value instead."""

                if not self.__headers_arrived:
                        self.__fill_headers()

                return self.__headers.get(hdr.lower(), default)

        def _prime(self):
                """Used by the underlying transport before handing this
                object off to other layers.  It ensures that the object's
                creator can catch errors that occur at connection time.
                All callers must still catch transport exceptions, however."""

                self.__fill_buffer(1)

        # Iterator methods

        def __iter__(self):
                return self

        def __next__(self):
                line = self.readline()
                if not line:
                        raise StopIteration
                return line

        next = __next__

        # Private methods
        
        def __fill_buffer(self, size=-1):
                """Call engine.run() to fill the file object's buffer.
                Read until we might block.  If size is specified, stop
                once we get at least size bytes, or might block,
                whichever comes first."""

                engine = self.__engine

                if not engine:
                        return False

                self.__lock.acquire()
                while 1:
                        if self.__done:
                                self.__lock.release()
                                return False
                        elif not engine.pending:
                                # nothing pending means no more transfer
                                self.__done = True
                                s = engine.check_status([self.__url])
                                if s:
                                        # Cleanup prior to raising exception
                                        self.__lock.release()
                                        if self.free_buffer:
                                                self.close()
                                        raise s[0]

                                self.__lock.release()
                                return False

                        try:
                                engine.run()
                        except tx.ExcessiveTransientFailure as ex:
                                s = engine.check_status([self.__url])
                                ex.failures = s
                                self.__lock.release()
                                if self.free_buffer:
                                        self.close()
                                raise
                        except:
                                # Cleanup and close, if exception
                                # raised by run.
                                self.__lock.release()
                                if self.free_buffer:
                                        self.close()
                                raise

                        if size > 0 and len(self.__buf) < size:
                                # loop if we need more data in the buffer
                                continue
                        else:
                                # break out of this loop
                                break

                self.__lock.release()
                return True

        def __fill_headers(self):
                """Run the transport until headers arrive.  When the data
                callback gets invoked, all headers have arrived.  The
                alternate scenario is when no data arrives, but the server
                isn't providing more input isi over the network.  In that case,
                the client either received just headers, or had the transfer
                close unexpectedly."""

                while not self.__data_callback_invoked:
                        if not self.__fill_buffer():
                                # We hit this case if we get headers
                                # but no data.
                                break

                self.__headers_arrived = True

        def __progress_callback(self, dltot, dlcur, ultot, ulcur):
                """Called by pycurl/libcurl framework to update
                progress tracking."""

                if self.__check_cancelation and self.__check_cancelation():
                        return -1

                return 0

        def __write_callback(self, data):
                """A callback given to transport engine that writes data
                into a buffer in this object."""

                if not self.__data_callback_invoked:
                        self.__data_callback_invoked = True

                # We don't force data to str here because data could be from a
                # gizpped file, which contains gzip magic number that can't be
                # decoded by 'utf-8'.
                self.__buf = self.__buf + data

        def __header_callback(self, data):
                """A callback given to the transport engine.  It reads header
                information from the transport.  This function saves
                the message from the http response, as well as a dictionary
                of headers that it can parse."""

                if data.startswith(b"HTTP/"):
                        rtup = data.split(None, 2)
                        try:
                                self.__httpmsg = rtup[2]
                        except IndexError:
                                pass

                elif data.find(b":") > -1:
                        k, v = data.split(b":", 1)
                        if v:
                                # convert to str as early as we can
                                self.__headers[force_str(k.lower())] = \
                                        force_str(v.strip())
