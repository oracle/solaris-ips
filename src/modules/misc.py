#!/usr/bin/python2.4
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

# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import errno
import httplib
import os
import platform
import re
import sha
import socket
import urllib
import urllib2
import urlparse
import sys
import zlib
import time
import calendar
import pkg.urlhelpers as urlhelpers
import pkg.portable as portable
from pkg.client.imagetypes import img_type_names, IMG_NONE
from pkg import VERSION

def time_to_timestamp(t):
        """ convert seconds since epoch to %Y%m%dT%H%M%SZ format"""
        # XXX optimize?
        return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(t))

def timestamp_to_time(ts):
        """ convert %Y%m%dT%H%M%SZ format to seconds since epoch"""
        # XXX optimize?
        return calendar.timegm(time.strptime(ts, "%Y%m%dT%H%M%SZ"))

def hash_file_name(f):
        """Return the two-level path fragment for the given filename, which is
        assumed to be a content hash of at least 8 distinct characters."""
        return os.path.join("%s" % f[0:2], "%s" % f[2:8], "%s" % f)

def url_affix_trailing_slash(u):
        if u[-1] != '/':
                u = u + '/'

        return u

_client_version = "pkg/%s (%s %s; %s %s; %%s)" % \
    (VERSION, portable.util.get_canonical_os_name(), platform.machine(),
    portable.util.get_os_release(), platform.version())

def versioned_urlopen(base_uri, operation, versions = [], tail = None,
    data = None, headers = {}, ssl_creds = None, imgtype = IMG_NONE):
        """Open the best URI for an operation given a set of versions.

        Both the client and the server may support multiple versions of
        the protocol of a particular operation.  The client will pass
        this method an ordered array of versions it understands, along
        with the base URI and the operation it wants.  This method will
        open the URL corresponding to the best version both the client
        and the server understand, returning a tuple of the open URL and
        the version used on success, and throwing an exception if no
        matching version can be found.
        """
        # Ignore http_proxy for localhost case, by overriding
        # default proxy behaviour of urlopen().
        netloc = urlparse.urlparse(base_uri)[1]

        if not netloc:
                raise ValueError, "Malformed URL: %s" % base_uri

        if urllib.splitport(netloc)[0] == "localhost":
                # XXX cache this opener?
                proxy_handler = urllib2.ProxyHandler({})
                opener_dir = urllib2.build_opener(proxy_handler)
                url_opener = opener_dir.open
        elif ssl_creds and ssl_creds != (None, None):
                cert_handler = urlhelpers.HTTPSCertHandler(
                    key_file = ssl_creds[0], cert_file = ssl_creds[1])
                opener_dir = urllib2.build_opener(cert_handler)
                url_opener = opener_dir.open
        else:
                url_opener = urllib2.urlopen

        for version in versions:
                if base_uri[-1] != '/':
                        base_uri += '/'

                if tail:
                        uri = urlparse.urljoin(base_uri, "%s/%s/%s" % \
                            (operation, version, tail))
                else:
                        uri = urlparse.urljoin(base_uri, "%s/%s" % \
                            (operation, version))

                headers["User-Agent"] = \
                    _client_version % img_type_names[imgtype]
                req = urllib2.Request(url = uri, headers = headers)
                if data is not None:
                        req.add_data(data)

                try:
                        c = url_opener(req)
                except urllib2.HTTPError, e:
                        if e.code != httplib.NOT_FOUND or \
                            e.msg != "Version not supported":
                                raise
                        continue
                # XXX catch BadStatusLine and convert to INTERNAL_SERVER_ERROR?

                return c, version
        else:
                # Couldn't find a version that we liked.
                raise RuntimeError, \
                    "%s doesn't speak a known version of %s operation" % \
                    (base_uri, operation)


_hostname_re = re.compile("^[a-zA-Z0-9](?:[a-zA-Z0-9\-]*[a-zA-Z0-9]+\.?)*$")
_invalid_host_chars = re.compile(".*[^a-zA-Z0-9\-\.]+")
_valid_proto = ["http", "https"]

def valid_auth_prefix(prefix):
        """Verify that the authority prefix only contains valid characters."""

        # This is a workaround for the the hostname_re being slow when
        # it comes to finding invalid characters in the prefix string.

        if _invalid_host_chars.match(prefix):
                # prefix bad chars
                return False

        if _hostname_re.match(prefix):
                return True

        return False

def valid_auth_url(url):
        """Verify that the authority URL contains only valid characters."""

        # First split the URL and check if the scheme is one we support
        o = urlparse.urlsplit(url)

        if not o[0] in _valid_proto:
                return False

        # Next verify that the network location is valid
        host, port = urllib.splitport(o[1])

        if not host or _invalid_host_chars.match(host):
                return False

        if _hostname_re.match(host):
                return True

        return False

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

class PipeError(Exception):
        """ Pipe exception. """

        def __init__(self, args=None):
                self.args = args

def msg(*text):
        """ Emit a message. """

        try:
                print ' '.join([str(l) for l in text])
        except IOError, e:
                if e.errno == errno.EPIPE:
                        raise PipeError, e
                raise

def emsg(*text):
        """ Emit a message to sys.stderr. """

        try:
                print >> sys.stderr, ' '.join([str(l) for l in text])
        except IOError, e:
                if e.errno == errno.EPIPE:
                        raise PipeError, e
                raise

def port_available(host, port):
        """Returns True if the indicated port is available to bind to;
        otherwise returns False."""

        port = int(port)
        if host is None:
                # None is the same as INADDR_ANY, which for our purposes,
                # should be the hostname.
                host = socket.gethostname()

        try:
                sock = None

                # Get the address family of our host (to allow for IPV6, etc.).
                for entry in socket.getaddrinfo(host, port, socket.AF_UNSPEC,
                    socket.SOCK_STREAM):
                        family, socktype, proto, canonname, sockaddr = entry

                        # First try to bind to the specified port to see if we
                        # have an access problem or some other issue.
                        sock = socket.socket(family, socktype, proto)
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR,
                            1)
                        sock.bind((host, port))
                        sock.close()

                        # Now try to connect to the specified port to see if it
                        # is already in use.
                        sock = socket.socket(family, socktype, proto)

                        # Some systems timeout rather than refuse a connection.
                        # This avoids getting stuck on SYN_SENT for those
                        # systems (such as certain firewalls).
                        sock.settimeout(1.0)

                        sock.connect((host, port))
                        sock.close()

                        # If we successfully connected...
                        raise socket.error(errno.EBUSY,
                            'Port already in use')

        except socket.error, e:
                errnum = e[0]
                try:
                        text = e[1]
                except IndexError:
                        text = e[0]

                if sock:
                        sock.close()

                if errnum == errno.ECONNREFUSED:
                        # If we could not connect to the port, we know it isn't
                        # in use.
                        return True, None

                return False, text

def bytes_to_str(bytes):
        """Returns a human-formatted string representing the number of bytes
        in the largest unit possible."""

        units = [
            ("B", 2**10),
            ("kB", 2**20),
            ("MB", 2**30),
            ("GB", 2**40),
            ("TB", 2**50),
            ("PB", 2**60),
            ("EB", 2**70)
        ]

        for uom, limit in units:
                if uom != "EB" and bytes >= limit:
                        # Try the next largest unit of measure unless this is
                        # the largest or if the byte size is within the current
                        # unit of measure's range.
                        continue
                else:
                        return "%.2f %s" % (round(bytes / float(
                            limit / 2**10), 2), uom)

def get_rel_path(request, uri):
        # Calculate the depth of the current request path relative to our base
        # uri. path_info always ends with a '/' -- so ignore it when
        # calculating depth.
        depth = request.path_info.count("/") - 1
        return ("../" * depth) + uri

def get_res_path(request, name):
        return get_rel_path(request, "%s/%s" % ("static", name))

# Set the maximum number of timeouts before we giveup.  This can
# be adjusted by setting the environment variable PKG_TIMEOUT_MAX
MAX_TIMEOUT_COUNT = 4

class TransferTimedOutException(Exception):
        def __init__(self, args = None):
                self.args = args


# Default maximum memory useage during indexing
# This is a soft cap since memory usage is estimated.
try:
        phys_pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        SERVER_DEFAULT_MEM_USE_KB = (phys_pages / 1024.0) * page_size / 3
        CLIENT_DEFAULT_MEM_USE_KB = SERVER_DEFAULT_MEM_USE_KB / 2.0

except:
        CLIENT_DEFAULT_MEM_USE_KB = 100
        SERVER_DEFAULT_MEM_USE_KB = 500
