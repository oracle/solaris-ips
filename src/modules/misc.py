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

# Copyright (c) 2007, 2010, Oracle and/or its affiliates. All rights reserved.

import calendar
import cStringIO
import datetime
import errno
import hashlib
import locale
import OpenSSL.crypto as osc
import operator
import os
import pkg.client.api_errors as api_errors
import pkg.portable as portable
import platform
import re
import shutil
import stat
import struct
import sys
import time
import urllib
import urlparse
import zlib

from pkg.client.imagetypes import img_type_names, IMG_NONE
from pkg import VERSION

# Minimum number of days to issue warning before a certificate expires
MIN_WARN_DAYS = datetime.timedelta(days=30)

# Copied from image.py as image.py can't be imported here (circular reference).
PKG_STATE_INSTALLED = 2

def get_release_notes_url():
        """Return a release note URL pointing to the correct release notes
           for this version"""

        # TBD: replace with a call to api.info() that can return a "release"
        # attribute of form YYYYMM against the SUNWsolnm package
        return "http://docs.sun.com/doc/821-1479"

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

_hostname_re = re.compile("^[a-zA-Z0-9](?:[a-zA-Z0-9\-]*[a-zA-Z0-9]+\.?)*$")
_invalid_host_chars = re.compile(".*[^a-zA-Z0-9\-\.]+")
_valid_proto = ["file", "http", "https"]

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

        if o[0] == "file":
                scheme, netloc, path, params, query, fragment = \
                    urlparse.urlparse(url, "file", allow_fragments=0)
                path = urllib.url2pathname(path)
                if not os.path.abspath(path):
                        return False
                # No further validation to be done.
                return True

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

        shasum = hashlib.sha1()
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
                self._args = args

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

def get_data_digest(data, length=None, return_content=False):
        """Returns a tuple of (SHA-1 hexdigest, content).

        'data' should be a file-like object or a pathname to a file.

        'length' should be an integer value representing the size of
        the contents of data in bytes.

        'return_content' is a boolean value indicating whether the
        second tuple value should contain the content of 'data' or
        if the content should be discarded during processing."""

        bufsz = 128 * 1024
        closefobj = False
        if isinstance(data, basestring):
                f = file(data, "rb", bufsz)
                closefobj = True
        else:
                f = data

        if length is None:
                length = os.stat(data).st_size

        # Read the data in chunks and compute the SHA1 hash as it comes in.  A
        # large read on some platforms (e.g. Windows XP) may fail.
        content = cStringIO.StringIO()
        fhash = hashlib.sha1()
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
        if closefobj:
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
                self._args = args

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

# A way to have a dictionary be a property

class DictProperty(object):
        class __InternalProxy(object):
                def __init__(self, obj, fget, fset, fdel, iteritems, keys, values, iterator):
                        self.__obj = obj
                        self.__fget = fget
                        self.__fset = fset
                        self.__fdel = fdel
                        self.__iteritems = iteritems
                        self.__keys = keys
                        self.__values = values
                        self.__iter = iterator

                def __getitem__(self, key):
                        if self.__fget is None:
                                raise AttributeError, "unreadable attribute"

                        return self.__fget(self.__obj, key)

                def __setitem__(self, key, value):
                        if self.__fset is None:
                                raise AttributeError, "can't set attribute"
                        self.__fset(self.__obj, key, value)

                def __delitem__(self, key):
                        if self.__fdel is None:
                                raise AttributeError, "can't delete attribute"
                        self.__fdel(self.__obj, key)

                def iteritems(self):
                        if self.__iteritems is None:
                                raise AttributeError, "can't iterate over items"
                        return self.__iteritems(self.__obj)

                def keys(self):
                        if self.__keys is None:
                                raise AttributeError, "can't iterate over keys"
                        return self.__keys(self.__obj)

                def values(self):
                        if self.__values is None:
                                raise AttributeError, "can't iterate over values"
                        return self.__values(self.__obj)

                def __iter__(self):
                        if self.__iter is None:
                                raise AttributeError, "can't iterate"
                        return self.__iter(self.__obj)

        def __init__(self, fget=None, fset=None, fdel=None, iteritems=None, 
            keys=None, values=None, iterator=None, doc=None):
                self.__fget = fget
                self.__fset = fset
                self.__fdel = fdel
                self.__iteritems = iteritems
                self.__doc__ = doc
                self.__keys = keys
                self.__values = values
                self.__iter = iterator

        def __get__(self, obj, objtype=None):
                if obj is None:
                        return self
                return self.__InternalProxy(obj, self.__fget, self.__fset, 
                    self.__fdel, self.__iteritems, self.__keys, self.__values, self.__iter)

        
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
                if e.errno == errno.EROFS:
                        raise api_errors.ReadOnlyFileSystemException(e.filename)
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

class Singleton(type):
        """Set __metaclass__ to Singleton to create a singleton.
        See http://en.wikipedia.org/wiki/Singleton_pattern """

        def __init__(self, name, bases, dictionary):
                super(Singleton, self).__init__(name, bases, dictionary)
                self.instance = None
 
        def __call__(self, *args, **kw):
                if self.instance is None:
                        self.instance = super(Singleton, self).__call__(*args, **kw)
 
                return self.instance

EmptyDict = ImmutableDict()

# Setting the python file buffer size to 128k gives substantial performance
# gains on certain files.
PKG_FILE_BUFSIZ = 128 * 1024

PKG_FILE_MODE = stat.S_IWUSR | stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH
PKG_DIR_MODE = (stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH |
    stat.S_IXOTH)
PKG_RO_FILE_MODE = stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH
