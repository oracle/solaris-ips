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
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

class StreamingFileObj(object):

        def __init__(self, url, engine):
                """Create a streaming file object that wraps around a
                transport engine.  This is only necessary if the underlying
                transport doesn't have its own streaming interface and the
                repo operation needs a streaming response."""

                self.__buf = ""
                self.__url = url
                self.__engine = engine
                self.__data_callback_invoked = False
                self.__headers_arrived = False
                self.__httpmsg = None
                self.__headers = {}
                self.__done = False

        def __del__(self):
                self.close()

        # File object methods

        def close(self):
                self.__buf = ""
                if not self.__done:
                        self.__engine.remove_request(self.__url)
                        self.__done = True
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

                if size < 0:
                        while self.__fill_buffer():
                                # just fill the buffer
                                pass
                        curdata = self.__buf
                        self.__buf = ""
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

                        self.__buf = ""
                        return curdata

        def readline(self, size=-1):
                """Read a line from the remote host.  If size is
                specified, read to newline or size, whichever is smaller."""

                if size < 0:
                        curdata = self.__buf
                        newline = curdata.find("\n")
                        if newline >= 0:
                                newline += 1
                                self.__buf = curdata[newline:]
                                return curdata[:newline]
                        while self.__fill_buffer():
                                newline = self.__buf.find("\n")
                                if newline >= 0:
                                        break

                        curdata = self.__buf
                        newline = curdata.find("\n")
                        if newline >= 0:
                                newline += 1
                                self.__buf = curdata[newline:]
                                return curdata[:newline]
                        self.__buf = ""
                        return curdata
                else:
                        curdata = self.__buf
                        newline = curdata.find("\n", 0, size)
                        datalen = len(curdata)
                        if newline >= 0:
                                newline += 1
                                self.__buf = curdata[newline:]
                                return curdata[:newline]
                        if datalen >= size:
                                self.__buf = curdata[size:]
                                return curdata[:size]
                        while self.__fill_buffer():
                                newline = self.__buf.find("\n", 0, size)
                                datalen = len(self.__buf)
                                if newline >= 0:
                                        break
                                if datalen >= size:
                                        break

                        curdata = self.__buf
                        newline = curdata.find("\n", 0, size)
                        datalen = len(curdata)
                        if newline >= 0:
                                newline += 1
                                self.__buf = curdata[newline:]
                                return curdata[:newline]
                        if datalen >= size:
                                self.__buf = curdata[size:]
                                return curdata[:size]
                        self.__buf = ""
                        return curdata

        def readlines(self, sizehint=0):
                """Read lines from the remote host, returning an
                array of the lines that were read.  sizehint specifies
                an approximate size, in bytes, of the total amount of data,
                as lines, that should be returned to the caller."""

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

        def get_write_func(self):
                return self.__write_callback

        def get_header_func(self):
                return self.__header_callback

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

                return self.__headers.get(hdr, default)

        def _prime(self):
                """Used by the underlying transport before handing this
                object off to other layers.  It ensures that the object's
                creator can catch errors that occur at connection time.
                All callers must still catch transport exceptions, however."""

                self.__fill_buffer(1)

        # Iterator methods

        def __iter__(self):
                return self

        def next(self):
                line = self.readline()
                if not line:
                        raise StopIteration
                return line

        # Private methods

        def __fill_buffer(self, size=-1):
                """Call engine.run() to fill the file object's buffer.
                Read until we might block.  If size is specified, stop
                once we get at least size bytes, or might block,
                whichever comes first."""

                engine = self.__engine

                while 1:
                        if not engine.pending:
                                # nothing pending means no more transfer
                                self.__done = True
                                s = engine.check_status([self.__url])
                                if len(s) > 0:
                                        # Cleanup prior to raising exception
                                        self.close()
                                        raise s[0]
                                return False

                        engine.run()

                        if size > 0 and len(self.__buf) < size:
                                # loop if we need more data in the buffer
                                continue
                        else:
                                # break out of this loop
                                break

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

        def __write_callback(self, data):
                """A callback given to transport engine that writes data
                into a buffer in this object."""

                if not self.__data_callback_invoked:
                        self.__data_callback_invoked = True

                self.__buf = self.__buf + data

        def __header_callback(self, data):
                """A callback given to the transport engine.  It reads header
                information from the transport.  This function saves
                the message from the http response, as well as a dictionary
                of headers that it can parse."""

                if data.startswith("HTTP/"):
                        rtup = data.split(None, 2)
                        try:
                                self.__httpmsg = rtup[2]
                        except IndexError:
                                pass

                elif data.find(":") > -1:
                        k, v = data.split(":", 1)
                        if v:
                                self.__headers[k] = v.strip()
