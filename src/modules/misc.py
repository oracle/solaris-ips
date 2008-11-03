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
import shutil
from stat import *

import pkg.urlhelpers as urlhelpers
import pkg.portable as portable
from pkg.client.imagetypes import img_type_names, IMG_NONE
from pkg import VERSION

def time_to_timestamp(t):
        """convert seconds since epoch to %Y%m%dT%H%M%SZ format"""
        # XXX optimize?
        return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(t))

def timestamp_to_time(ts):
        """convert %Y%m%dT%H%M%SZ format to seconds since epoch"""
        # XXX optimize?
        return calendar.timegm(time.strptime(ts, "%Y%m%dT%H%M%SZ"))

def copyfile(src_path, dst_path):
        """copy a file, preserving attributes, ownership, etc. where possible"""
        stat = os.lstat(src_path)
        shutil.copy2(src_path, dst_path)
        try:
                portable.chown(dst_path, stat.st_uid, stat.st_gid)
        except OSError, e:
                if e.errno != errno.EPERM:
                        raise

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

def versioned_urlopen(base_uri, operation, versions = None, tail = None,
    data = None, headers = None, ssl_creds = None, imgtype = IMG_NONE,
    method = "GET", uuid = None):
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

        if not versions:
                versions = []

        if not headers:
                headers = {}

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
                if uuid:
                        headers["X-IPkg-UUID"] = uuid
                req = urllib2.Request(url = uri, headers = headers)
                if method == "HEAD":
                        # Must override urllib2's get_method since it doesn't
                        # natively support this operation.
                        req.get_method = lambda: "HEAD"
                elif data is not None:
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

class FilelikeString(object):
        def __init__(self):
                self.buf = ""

        def write(self, o):
                self.buf += o

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
                raise zlib.error, "Not a gzipped file"
        method = ord(gz.read(1))
        if method != 8:
                raise zlib.error, "Unknown compression method"
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
                        sock.bind(sockaddr)
                        sock.close()

                        # Now try to connect to the specified port to see if it
                        # is already in use.
                        sock = socket.socket(family, socktype, proto)

                        # Some systems timeout rather than refuse a connection.
                        # This avoids getting stuck on SYN_SENT for those
                        # systems (such as certain firewalls).
                        sock.settimeout(1.0)

                        try:
                                sock.connect(sockaddr)
                        except socket.timeout:
                                # handle this at the next level
                                raise
                        except socket.error, e:
                                errnum = e[0]
                                if errnum != errno.EINVAL:
                                        raise
                                # this BSD-based system has trouble with a 
                                # non-blocking failed connect
                                sock.close()
                                sock = socket.socket(family, socktype, proto)
                                sock.connect(sockaddr)
                                
                        sock.close()

                        # If we successfully connected...
                        raise socket.error(errno.EBUSY,
                            'Port already in use')

        except socket.timeout, t:
                return True, None

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
            (_("B"), 2**10),
            (_("kB"), 2**20),
            (_("MB"), 2**30),
            (_("GB"), 2**40),
            (_("TB"), 2**50),
            (_("PB"), 2**60),
            (_("EB"), 2**70)
        ]

        for uom, limit in units:
                if uom != _("EB") and bytes >= limit:
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

def get_pkg_otw_size(action):
        """Takes a file action and returns the over-the-wire size of
        a package as an integer.  The OTW size is the compressed size,
        pkg.csize.  If that value isn't available, it returns pkg.size.
        If pkg.size isn't available, return zero."""

        size = action.attrs.get("pkg.csize", 0)
        if size == 0:
                size = action.attrs.get("pkg.size", 0)

        return int(size)

class TransportException(Exception):
        """ Abstract base class for various transport exceptions """
        def __init__(self):
                self.count = 1

class TransportFailures(TransportException):
        """ This exception encapsulates multiple transport exceptions """

        #
        # This class is a subclass of TransportException so that calling
        # code can reasonably 'except TransportException' and get either
        # a single-valued or in this case a multi-valued instance.
        #
        def __init__(self):
                TransportException.__init__(self)
                self.exceptions = []

        def append(self, exc):
                assert isinstance(exc, TransportException)
                for x in self.exceptions:
                        if cmp(x, exc) == 0:
                                x.count += 1
                                return

                self.exceptions.append(exc)

        def __str__(self):
                if len(self.exceptions) == 0:
                        return "[no errors accumulated]"

                s = ""
                for i, x in enumerate(self.exceptions):
                        if len(self.exceptions) > 1:
                                s += "%d: " % (i + 1)
                        s += str(x)
                        if x.count > 1:
                                s += " (happened %d times)" % x.count
                        s += "\n"
                return s


class TransferTimedOutException(TransportException):
        """Raised when the transfer times out, or is terminated with a
        retryable error."""
        def __init__(self, url, reason=None):
                TransportException.__init__(self)
                self.url = url
                self.reason = reason

        def __str__(self):
                s = "Transfer from '%s' timed out" % self.url
                if self.reason:
                        s += ": %s" % self.reason
                s += "."
                return s

        def __cmp__(self, other):
                if not isinstance(other, TransferTimedOutException):
                        return -1        
                r = cmp(self.url, other.url)
                if r != 0:
                        return r
                return cmp(self.reason, other.reason)


# Retryable http errors.  These are the HTTP errors that we'll catch.  When we
# catch them, we throw a TransferTimedOutException instead re-raising the
# HTTPError and letting some other handler catch it.

# XXX consider moving to pkg.client module
retryable_http_errors = set((httplib.REQUEST_TIMEOUT, httplib.BAD_GATEWAY,
        httplib.GATEWAY_TIMEOUT))
retryable_socket_errors = set((errno.ECONNABORTED, errno.ECONNRESET,
        errno.ECONNREFUSED))


class TransferContentException(TransportException):
        """Raised when there are problems downloading the requested content."""
        def __init__(self, url, reason=None):
                TransportException.__init__(self)
                self.url = url
                self.reason = reason

        def __str__(self):
                s = "Transfer from '%s' failed" % self.url
                if self.reason:
                        s += ": %s" % self.reason
                s += "."
                return s

        def __cmp__(self, other):
                if not isinstance(other, TransferContentException):
                        return -1        
                r = cmp(self.url, other.url)
                if r != 0:
                        return r
                return cmp(self.reason, other.reason)

class TruncatedTransferException(TransportException):
        """Raised when the transfer that was received doesn't match the
        expected length."""
        def __init__(self, url, recd=-1, expected=-1):
                TransportException.__init__(self)
                self.url = url
                self.recd = recd
                self.expected = expected

        def __str__(self):
                s = "Transfer from '%s' unexpectedly terminated" % self.url
                if self.recd > -1 and self.expected > -1:
                        s += ": received %d of %d bytes" % (self.recd,
                            self.expected)
                s += "."
                return s

        def __cmp__(self, other):
                if not isinstance(other, TruncatedTransferException):
                        return -1        
                r = cmp(self.url, other.url)
                if r != 0:
                        return r
                r = cmp(self.expected, other.expected)
                if r != 0:
                        return r
                return cmp(self.recd, other.recd)


class InvalidContentException(TransportException):
        """Raised when the content's hash/chash doesn't verify, or the
        content is received in an unreadable format."""
        def __init__(self, path, data):
                TransportException.__init__(self)
                self.path = path
                self.data = data

        def __str__(self):
                s = "Invalid content for action with path %s" % self.path
                if self.data:
                        s += " %s." % self.data
                return s

        def __cmp__(self, other):
                if not isinstance(other, InvalidContentException):
                        return -1        
                r = cmp(self.path, other.path)
                if r != 0:
                        return r
                return cmp(self.data, other.data)


# Default maximum memory useage during indexing
# This is a soft cap since memory usage is estimated.
try:
        phys_pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        SERVER_DEFAULT_MEM_USE_KB = (phys_pages / 1024.0) * page_size / 3
        CLIENT_DEFAULT_MEM_USE_KB = SERVER_DEFAULT_MEM_USE_KB / 2.0
except KeyboardInterrupt:
        raise
except:
        CLIENT_DEFAULT_MEM_USE_KB = 100
        SERVER_DEFAULT_MEM_USE_KB = 500

