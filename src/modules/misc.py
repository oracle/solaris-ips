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

# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import calendar
import cStringIO
import datetime
import errno
import httplib
import locale
import OpenSSL.crypto as osc
import operator
import os
import pkg.client.api_errors as api_errors
import pkg.portable as portable
import pkg.urlhelpers as urlhelpers
import platform
import re
import sha
import shutil
import socket
import struct
import sys
import time
import urllib
import urllib2
import urlparse
import zlib

from pkg.client.imagetypes import img_type_names, IMG_NONE
from pkg.client import global_settings
from pkg import VERSION

# Minimum number of days to issue warning before a certificate expires
MIN_WARN_DAYS = datetime.timedelta(days=30)

def get_release_notes_url():
        """Return a release note URL pointing to the correct release notes
           for this version"""

        # TBD: replace with a call to api.info() that can return a "release"
        # attribute of form YYYYMM against the SUNWsolnm package
        release_str = \
                "http://opensolaris.org/os/project/indiana/resources/relnotes/200906/"
        if platform.processor() == 'sparc':
                release_str += 'sparc/'
        else:
                release_str += 'x86/'

        return release_str

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
        fs = os.lstat(src_path)
        shutil.copy2(src_path, dst_path)
        try:
                portable.chown(dst_path, fs.st_uid, fs.st_gid)
        except OSError, e:
                if e.errno != errno.EPERM:
                        raise
def expanddirs(dirs):
        """given a set of directories, return expanded set that includes
        all components"""
        out = set()
        for d in dirs:
                p = d
                while p != "":
                        out.add(p)
                        p = os.path.dirname(p)
        return out

def hash_file_name(f):
        """Return the two-level path fragment for the given filename, which is
        assumed to be a content hash of at least 8 distinct characters."""
        return os.path.join("%s" % f[0:2], "%s" % f[2:8], "%s" % f)

def url_affix_trailing_slash(u):
        if u[-1] != '/':
                u = u + '/'

        return u

_client_version = "pkg/%s (%s %s; %s %s; %%s; %%s)" % \
    (VERSION, portable.util.get_canonical_os_name(), platform.machine(),
    portable.util.get_os_release(), platform.version())

def user_agent_str(img, client_name):

        if not img or img.type is None:
                imgtype = IMG_NONE
        else:
                imgtype = img.type

        useragent = _client_version % (img_type_names[imgtype], client_name)

        return useragent

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
                opener_dir = urllib2.build_opener(
                    urlhelpers.HTTPSProxyHandler, cert_handler)
                url_opener = opener_dir.open
        else:
                url_opener = urllib2.urlopen

        if not versions:
                versions = []

        if not headers:
                headers = {}

        for i, version in enumerate(versions):
                if base_uri[-1] != '/':
                        base_uri += '/'

                if tail:
                        tail_str = tail
                        if isinstance(tail, list):
                                tail_str = tail[i]
                        uri = urlparse.urljoin(base_uri, "%s/%s/%s" % \
                            (operation, version, tail_str))
                else:
                        uri = urlparse.urljoin(base_uri, "%s/%s" % \
                            (operation, version))

                headers["User-Agent"] = \
                    _client_version % (img_type_names[imgtype],
                        global_settings.client_name)
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
                        if e.code != httplib.NOT_FOUND:
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

def valid_pub_prefix(prefix):
        """Verify that the publisher prefix only contains valid characters."""

        if not prefix:
                return False

        # This is a workaround for the the hostname_re being slow when
        # it comes to finding invalid characters in the prefix string.
        if _invalid_host_chars.match(prefix):
                # prefix bad chars
                return False

        if _hostname_re.match(prefix):
                return True

        return False

def valid_pub_url(url):
        """Verify that the publisher URL contains only valid characters."""

        if not url:
                return False

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

def setlocale(category, loc=None, printer=None):
        """Wraps locale.setlocale(), falling back to the C locale if the desired
        locale is broken or unavailable.  The 'printer' parameter should be a
        function which takes a string and displays it.  If 'None' (the default),
        setlocale() will print the message to stderr."""

        if printer is None:
                printer = emsg

        try:
                locale.setlocale(category, loc)
                # Because of Python bug 813449, getdefaultlocale may fail
                # with a ValueError even if setlocale succeeds. So we call
                # it here to prevent having this error raised if it is 
                # called later by other non-pkg(5) code.
                locale.getdefaultlocale()
        except (locale.Error, ValueError):
                try:
                        dl = " '%s.%s'" % locale.getdefaultlocale()
                except ValueError:
                        dl = ""
                printer("Unable to set locale%s; locale package may be broken "
                    "or\nnot installed.  Reverting to C locale." % dl)
                locale.setlocale(category, "C")

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

def bytes_to_str(bytes, format=None):
        """Returns a human-formatted string representing the number of bytes
        in the largest unit possible.  If provided, 'format' should be a string
        which can be formatted with a dictionary containing a float 'num' and
        string 'unit'."""

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
                        if not format:
                                format = "%(num).2f %(unit)s"
                        return format % {
                            "num": round(bytes / float(limit / 2**10), 2),
                            "unit": uom
                        }

def get_rel_path(request, uri):
        # Calculate the depth of the current request path relative to our base
        # uri. path_info always ends with a '/' -- so ignore it when
        # calculating depth.
        depth = request.path_info.count("/") - 1
        return ("../" * depth) + uri

def get_pkg_otw_size(action):
        """Takes a file action and returns the over-the-wire size of
        a package as an integer.  The OTW size is the compressed size,
        pkg.csize.  If that value isn't available, it returns pkg.size.
        If pkg.size isn't available, return zero."""

        size = action.attrs.get("pkg.csize", 0)
        if size == 0:
                size = action.attrs.get("pkg.size", 0)

        return int(size)

def get_inventory_list(image, pargs, all_known, all_versions):
        most_recent = {}
        installed = []
        res = image.inventory(pargs, all_known, ordered=not all_versions)
        # All_Versions reduces the output so that only the most recent
        # version and installed version of packages appear.
        if all_versions:
                for pfmri, state in res:
                        if state["state"] == "installed":
                                installed.append((pfmri, state))
                        hv = pfmri.get_pkg_stem(include_scheme=False)
                        if hv in most_recent:
                                stored_pfmri, stored_state = \
                                    most_recent[hv]
                                if pfmri.is_successor(stored_pfmri):
                                        most_recent[hv] = (pfmri, state)
                        else:
                                most_recent[hv] = (pfmri, state)
                res = installed + most_recent.values()

                # This method is necessary because fmri.__cmp__ does
                # not provide the desired ordering. It uses the same
                # ordering on package names as fmri.__cmp__ but it
                # reverse sorts on version, so that 98 comes before 97.
                # Also, publishers are taken into account so that
                # preferred publishers come before others. Finally,
                # publishers are presented in alphabetical order.
                def __fmri_cmp((f1, s1), (f2, s2)):
                        t = cmp(f1.pkg_name, f2.pkg_name)
                        if t != 0:
                                return t
                        t = cmp(f2, f1)
                        if t != 0:
                                return t
                        if f1.preferred_publisher():
                                return -1
                        if f2.preferred_publisher():
                                return 1
                        return cmp(f1.get_publisher(),
                            f2.get_publisher())
                
                res.sort(cmp=__fmri_cmp)
        return res

def get_data_digest(data, length=None, return_content=False):
        """Returns a tuple of (SHA-1 hexdigest, content).

        'data' should be a file-like object or a pathname to a file.

        'length' should be an integer value representing the size of
        the contents of data in bytes.

        'return_content' is a boolean value indicating whether the
        second tuple value should contain the content of 'data' or
        if the content should be discarded during processing."""

        bufsz = 128 * 1024
        if isinstance(data, basestring):
                f = file(data, "rb", bufsz)
        else:
                f = data

        if length is None:
                length = os.stat(data).st_size

        # Read the data in chunks and compute the SHA1 hash as it comes in.  A
        # large read on some platforms (e.g. Windows XP) may fail.
        content = cStringIO.StringIO()
        fhash = sha.new()
        while length > 0:
                data = f.read(min(bufsz, length))
                if return_content:
                        content.write(data)
                fhash.update(data)

                l = len(data)
                if l == 0:
                        break
                length -= l
        content.reset()
        f.close()

        return fhash.hexdigest(), content.read()

def __getvmusage():
        """Return the amount of virtual memory in bytes currently in use."""

        # This works only on Solaris, in 32-bit mode.  It may not work on older
        # or newer versions than 5.11.  Ideally, we would use libproc, or check
        # sbrk(0), but this is expedient.  In most cases (there's a small chance
        # the file will decode, but incorrectly), failure will raise an
        # exception, and we'll fail safe.
        try:
                # Read just the psinfo_t, not the tacked-on lwpsinfo_t
                psinfo_arr = file("/proc/self/psinfo").read(232)
                psinfo = struct.unpack("6i5I4LHH6L16s80siiIIc3x7i", psinfo_arr)
                vsz = psinfo[11] * 1024
        except Exception:
                vsz = None

        return vsz

def out_of_memory():
        """Return an out of memory message, for use in a MemoryError handler."""

        vsz = bytes_to_str(__getvmusage(), format="%(num).0f%(unit)s")

        if vsz is not None:
                error = """\
There is not enough memory to complete the requested operation.  At least
%(vsz)s of virtual memory was in use by this command before it ran out of memory.
You must add more memory (swap or physical) or allow the system to access more
existing memory, or quit other programs that may be consuming memory, and try
the operation again."""
        else:
                error = """\
There is not enough memory to complete the requested operation.  You must
add more memory (swap or physical) or allow the system to access more existing
memory, or quit other programs that may be consuming memory, and try the
operation again."""

        return _(error) % locals()


class CfgCacheError(Exception):
        """Thrown when there are errors with the cfg cache."""
        def __init__(self, args=None):
                self.args = args

# ImmutableDict and EmptyI for argument defaults
EmptyI = tuple()

class ImmutableDict(dict):
        def __init__(self, default=EmptyI):
                dict.__init__(self, default)

        def __setitem__(self, item, value):
                self.__oops()

        def __delitem__(self, item, value):
                self.__oops()

        def pop(self, item, default=None):
                self.__oops()

        def popitem(self):
                self.__oops()

        def setdefault(self, item, default=None):
                self.__oops()

        def update(self, d):
                self.__oops()

        def copy(self):
                return ImmutableDict()

        def clear(self):
                self.__oops()

        def __oops(self):
                raise TypeError, "Item assignment to ImmutableDict"

def get_sorted_publishers(pubs, preferred=None):
        spubs = []
        for p in sorted(pubs, key=operator.attrgetter("prefix")):
                if preferred and preferred == p.prefix:
                        spubs.insert(0, p)
                else:
                        spubs.append(p)
        return spubs

def build_cert(path, uri=None, pub=None):
        """Take the file given in path, open it, and use it to create
        an X509 certificate object.

        'uri' is an optional value indicating the uri associated with or that
        requires the certificate for access.

        'pub' is an optional string value containing the name (prefix) of a
        related publisher."""

        try:
                cf = file(path, "rb")
                certdata = cf.read()
                cf.close()
        except EnvironmentError, e:
                if e.errno == errno.ENOENT:
                        raise api_errors.NoSuchCertificate(path, uri=uri,
                            publisher=pub)
                if e.errno == errno.EACCES:
                        raise api_errors.PermissionsException(e.filename)
                raise

        try:
                return osc.load_certificate(osc.FILETYPE_PEM, certdata)
        except osc.Error, e:
                # OpenSSL.crypto.Error
                raise api_errors.InvalidCertificate(path, uri=uri,
                    publisher=pub)

def validate_ssl_cert(ssl_cert, prefix=None, uri=None):
        """Validates the indicated certificate and returns a pyOpenSSL object
        representing it if it is valid."""
        cert = build_cert(ssl_cert, uri=uri, pub=prefix)

        if cert.has_expired():
                raise api_errors.ExpiredCertificate(ssl_cert, uri=uri,
                    publisher=prefix)

        now = datetime.datetime.utcnow()
        nb = cert.get_notBefore()
        t = time.strptime(nb, "%Y%m%d%H%M%SZ")
        nbdt = datetime.datetime.utcfromtimestamp(
            calendar.timegm(t))

        # PyOpenSSL's has_expired() doesn't validate the notBefore
        # time on the certificate.  Don't ask me why.

        if nbdt > now:
                raise api_errors.NotYetValidCertificate(ssl_cert, uri=uri,
                    publisher=prefix)

        na = cert.get_notAfter()
        t = time.strptime(na, "%Y%m%d%H%M%SZ")
        nadt = datetime.datetime.utcfromtimestamp(
            calendar.timegm(t))

        diff = nadt - now

        if diff <= MIN_WARN_DAYS:
                raise api_errors.ExpiringCertificate(ssl_cert, uri=uri,
                    publisher=prefix, days=diff.days)

        return cert

EmptyDict = ImmutableDict()

# Setting the python file buffer size to 128k gives substantial performance
# gains on certain files.
PKG_FILE_BUFSIZ = 128 * 1024
