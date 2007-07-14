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
# Copyright 2007 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

"""module describing a generic packaging object

This module contains the Action class, which represents a generic packaging
object.  It also contains a helper function, gunzip_from_stream(), which actions
may use to decompress their data payloads."""

import sha
import zlib

import pkg.actions

def gunzip_from_stream(gz, outfile):
        """Decompress a gzipped input stream into an output stream.

        The argument 'gz' is an input stream of a gzipped file (XXX make it do
        either a gzipped file or raw zlib compressed data), and 'outfile' is is
        an output stream.  gunzip_from_stream() decompresses data from 'gz' and
        writes it to 'outfile', and returns the hexadecimal SHA-1 sum of that
        data.
        """

        FHCRC = 2
        FEXTRA = 4
        FNAME = 8
        FCOMMENT = 16

        # Read the header
        magic = gz.read(2)
        if magic != "\037\213":
                raise IOError, "Not a gzipped file"
        method = ord(gz.read(1))
        if method != 8:
                raise IOError, "Unknown compression method"
        flag = ord(gz.read(1))
        gz.read(6) # Discard modtime, extraflag, os

        # Discard an extra field
        if flag & FEXTRA:
                xlen = ord(gz.read(1))
                xlen = xlen + 256 * ord(gz.read(1))
                gz.read(xlen)

        # Discard a null-terminated filename
        if flag & FNAME:
                while True:
                        s = gz.read(1)
                        if not s or s == "\000":
                                break

        # Discard a null-terminated comment
        if flag & FCOMMENT:
                while True:
                        s = gz.read(1)
                        if not s or s == "\000":
                                break

        # Discard a 16-bit CRC
        if flag & FHCRC:
                gz.read(2)

        shasum = sha.new()
        dcobj = zlib.decompressobj(-zlib.MAX_WBITS)

        while True:
                buf = gz.read(64 * 1024)
                if buf == "":
                        ubuf = dcobj.flush()
                        shasum.update(ubuf)
                        outfile.write(ubuf)
                        break
                ubuf = dcobj.decompress(buf)
                shasum.update(ubuf)
                outfile.write(ubuf)

        return shasum.hexdigest()

class Action(object):
        """Class representing a generic packaging object.

        An Action is a very simple wrapper around two dictionaries: a named set
        of data streams and a set of attributes.  Data streams generally
        represent files on disk, and attributes represent metadata about those
        files.
        """

        name = "generic"
        attributes = ()

        def __init__(self, data=None, **attrs):
                """Action constructor.

                The optional 'data' argument may be either a string, a file-like
                object, or a callable.  If it is a string, then it will be
                substituted with a callable that will return an open handle to
                the file represented by the string.  Otherwise, if it is not
                already a callable, it is assumed to be a file-like object, and
                will be substituted with a callable that will return the object.
                If it is a callable, it will not be replaced at all.

                Any remaining named arguments will be treated as attributes.
                """
                self.attrs = attrs

                if isinstance(data, str):
                        def file_opener():
                                return open(data)
                        self.data = file_opener
                elif not callable(data) and data != None:
                        def data_opener():
                                return data
                        self.data = data_opener
                else:
                        self.data = data

        def __str__(self):
                """Serialize the action into manifest form.

                The form is the name, followed by the hash, if it exists,
                followed by attributes in the form 'key=value'.  All fields are
                space-separated, which for now means that no tokens may have
                spaces (though they may have '=' signs).

                Note that an object with a datastream may have been created in
                such a way that the hash field is not populated, or not
                populated with real data.  The action classes do not guarantee
                that at the time that __str__() is called, the hash is properly
                computed.  This may need to be done externally.
                """
                str = self.name
                if hasattr(self, "hash"):
                        str += " " + self.hash

                def q(s):
                        if " " in s:
                                return '"%s"' % s
                        else:
                                return s

                stringattrs = [
                    "%s=%s" % (k, q(self.attrs[k]))
                    for k in self.attrs
                    if not isinstance(self.attrs[k], list)
                ]

                listattrs = [
                    " ".join([
                        "%s=%s" % (k, q(lmt))
                        for lmt in self.attrs[k]
                    ])
                    for k in self.attrs
                    if isinstance(self.attrs[k], list)
                ]

                return " ".join([str] + stringattrs + listattrs)

        def __cmp__(self, other):
                types = pkg.actions.types

                # Sort directories by path
                if type(self) == types["dir"] == type(other):
                        return cmp(self.attrs["path"], other.attrs["path"])
                # Directories come before anything else
                elif type(self) == types["dir"] != type(other):
                        return -1
                elif type(self) != types["dir"] == type(other):
                        return 1
                # Resort to the default comparison
                else:
                        return cmp(id(self), id(other))

        def preinstall(self, image):
                """Client-side method that performs pre-install actions."""
                pass

        def install(self, image):
                """Client-side method that installs the object."""
                pass

        def postinstall(self):
                """Client-side method that performs post-install actions."""
                pass
