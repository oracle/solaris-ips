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

# Copyright (c) 2007, 2011, Oracle and/or its affiliates. All rights reserved.

import OpenSSL.crypto as osc
import cStringIO
import calendar
import datetime
import errno
import getopt
import hashlib
import locale
import os
import platform
import re
import shutil
import simplejson as json
import stat
import struct
import sys
import time
import urllib
import urlparse
import zlib

import pkg.client.api_errors as api_errors
import pkg.portable as portable

from pkg import VERSION
from pkg.client import global_settings
from pkg.client.debugvalues import DebugValues
from pkg.client.imagetypes import img_type_names, IMG_NONE
from pkg.pkggzip import PkgGzipFile

# Minimum number of days to issue warning before a certificate expires
MIN_WARN_DAYS = datetime.timedelta(days=30)

# Copied from image.py as image.py can't be imported here (circular reference).
PKG_STATE_INSTALLED = 2

# Constant string used across many modules as a property name.
SIGNATURE_POLICY = "signature-policy"

# Bug URI Constants (deprecated)
BUG_URI_CLI = "https://defect.opensolaris.org/bz/enter_bug.cgi?product=pkg&component=cli"
BUG_URI_GUI = "https://defect.opensolaris.org/bz/enter_bug.cgi?product=pkg&component=gui"

# Traceback message.
def get_traceback_message():
        """This function returns the standard traceback message.  A function
        is necessary since the _() call must be done at runtime after locale
        setup."""

        return _("""\n
This is an internal error in pkg(5) version %(version)s.  Please log a
Service Request about this issue including the information above and this
message.""") % { "version": VERSION }

def get_release_notes_url():
        """Return a release note URL pointing to the correct release notes
           for this version"""

        # TBD: replace with a call to api.info() that can return a "release"
        # attribute of form YYYYMM against the SUNWsolnm package
        return "http://www.oracle.com/pls/topic/lookup?ctx=E23824&id=SERNS"

def time_to_timestamp(t):
        """convert seconds since epoch to %Y%m%dT%H%M%SZ format"""
        # XXX optimize?
        return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(t))

def timestamp_to_time(ts):
        """convert %Y%m%dT%H%M%SZ format to seconds since epoch"""
        # XXX optimize?
        return calendar.timegm(time.strptime(ts, "%Y%m%dT%H%M%SZ"))

def timestamp_to_datetime(ts):
        """convert %Y%m%dT%H%M%SZ format to a datetime object"""
        return datetime.datetime.strptime(ts,"%Y%m%dT%H%M%SZ")

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

_hostname_re = re.compile("^[a-zA-Z0-9\[](?:[a-zA-Z0-9\-:]*[a-zA-Z0-9:\]]+\.?)*$")
_invalid_host_chars = re.compile(".*[^a-zA-Z0-9\-\.:\[\]]+")
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
def N_(message):
        """Return its argument; used to mark strings for localization when
        their use is delayed by the program."""
        return message

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

def get_rel_path(request, uri, pub=None):
        # Calculate the depth of the current request path relative to our base
        # uri. path_info always ends with a '/' -- so ignore it when
        # calculating depth.
        rpath = request.path_info
        if pub:
                rpath = rpath.replace("/%s/" % pub, "/")
        depth = rpath.count("/") - 1
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

def compute_compressed_attrs(fname, file_path, data, size, compress_dir,
    bufsz=64*1024):
        """Returns the size and hash of the compressed data.  If the file
        located at file_path doesn't exist or isn't gzipped, it creates a file
        in compress_dir named fname."""

        #
        # This check prevents compressing a file which is already compressed.
        # This takes CPU load off the depot on large imports of mostly-the-same
        # stuff.  And in general it saves disk bandwidth, and on ZFS in
        # particular it saves us space in differential snapshots.  We also need
        # to check that the destination is in the same compression format as
        # the source, as we must have properly formed files for chash/csize
        # properties to work right.
        #

        fileneeded = True
        if file_path:
                if PkgGzipFile.test_is_pkggzipfile(file_path):
                        fileneeded = False
                        opath = file_path

        if fileneeded:
                opath = os.path.join(compress_dir, fname)
                ofile = PkgGzipFile(opath, "wb")

                nbuf = size / bufsz

                for n in range(0, nbuf):
                        l = n * bufsz
                        h = (n + 1) * bufsz
                        ofile.write(data[l:h])

                m = nbuf * bufsz
                ofile.write(data[m:])
                ofile.close()

        data = None

        # Now that the file has been compressed, determine its
        # size.
        fs = os.stat(opath)
        csize = str(fs.st_size)

        # Compute the SHA hash of the compressed file.  In order for this to
        # work correctly, we have to use the PkgGzipFile class.  It omits
        # filename and timestamp information from the gzip header, allowing us
        # to generate deterministic hashes for different files with identical
        # content.
        cfile = open(opath, "rb")
        chash = hashlib.sha1()
        while True:
                cdata = cfile.read(bufsz)
                if cdata == "":
                        break
                chash.update(cdata)
        cfile.close()
        return csize, chash

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
                def __init__(self, obj, fget, fset, fdel, iteritems, keys,
                    values, iterator, fgetdefault, fsetdefault, update, pop):
                        self.__obj = obj
                        self.__fget = fget
                        self.__fset = fset
                        self.__fdel = fdel
                        self.__iteritems = iteritems
                        self.__keys = keys
                        self.__values = values
                        self.__iter = iterator
                        self.__fgetdefault = fgetdefault
                        self.__fsetdefault = fsetdefault
                        self.__update = update
                        self.__pop = pop

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
                                raise AttributeError, "can't iterate over " \
                                    "values"
                        return self.__values(self.__obj)

                def get(self, key, default=None):
                        if self.__fgetdefault is None:
                                raise AttributeError, "can't use get"
                        return self.__fgetdefault(self.__obj, key, default)

                def setdefault(self, key, default=None):
                        if self.__fsetdefault is None:
                                raise AttributeError, "can't use setdefault"
                        return self.__fsetdefault(self.__obj, key, default)

                def update(self, d):
                        if self.__update is None:
                                raise AttributeError, "can't use update"
                        return self.__update(self.__obj, d)

                def pop(self, d, default):
                        if self.__pop is None:
                                raise AttributeError, "can't use pop"
                        return self.__pop(self.__obj, d, default)

                def __iter__(self):
                        if self.__iter is None:
                                raise AttributeError, "can't iterate"
                        return self.__iter(self.__obj)

        def __init__(self, fget=None, fset=None, fdel=None, iteritems=None,
            keys=None, values=None, iterator=None, doc=None, fgetdefault=None,
            fsetdefault=None, update=None, pop=None):
                self.__fget = fget
                self.__fset = fset
                self.__fdel = fdel
                self.__iteritems = iteritems
                self.__doc__ = doc
                self.__keys = keys
                self.__values = values
                self.__iter = iterator
                self.__fgetdefault = fgetdefault
                self.__fsetdefault = fsetdefault
                self.__update = update
                self.__pop = pop

        def __get__(self, obj, objtype=None):
                if obj is None:
                        return self
                return self.__InternalProxy(obj, self.__fget, self.__fset,
                    self.__fdel, self.__iteritems, self.__keys, self.__values,
                    self.__iter, self.__fgetdefault, self.__fsetdefault,
                    self.__update, self.__pop)


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

# Used for the conversion of the signature value between hex and binary.
char_list = "0123456789abcdef"

def binary_to_hex(s):
        """Converts a string of bytes to a hexadecimal representation.
        """

        res = ""
        for i, p in enumerate(s):
                p = ord(p)
                a = char_list[p % 16]
                p = p/16
                b = char_list[p % 16]
                res += b + a
        return res

def hex_to_binary(s):
        """Converts a string of hex digits to the binary representation.
        """

        res = ""
        for i in range(0, len(s), 2):
                res += chr(char_list.find(s[i]) * 16 +
                    char_list.find(s[i+1]))
        return res

def config_temp_root():
        """Examine the environment.  If the environment has set TMPDIR, TEMP,
        or TMP, return None.  This tells tempfile to use the environment
        settings when creating temporary files/directories.  Otherwise,
        return a path that the caller should pass to tempfile instead."""

        default_root = "/var/tmp"

        # In Python's tempfile module, the default temp directory
        # includes some paths that are suboptimal for holding large numbers
        # of files.  If the user hasn't set TMPDIR, TEMP, or TMP in the
        # environment, override the default directory for creating a tempfile.
        tmp_envs = [ "TMPDIR", "TEMP", "TMP" ]
        for ev in tmp_envs:
                env_val = os.getenv(ev)
                if env_val:
                        return None

        return default_root

def parse_uri(uri, cwd=None):
        """Parse the repository location provided and attempt to transform it
        into a valid repository URI.

        'cwd' is the working directory to use to turn paths into an absolute
        path.  If not provided, the current working directory is used.
        """

        if uri.find("://") == -1 and not uri.startswith("file:/"):
                # Convert the file path to a URI.
                if not cwd:
                        uri = os.path.abspath(uri)
                elif not os.path.isabs(uri):
                        uri = os.path.normpath(os.path.join(cwd, uri))

                uri = urlparse.urlunparse(("file", "",
                    urllib.pathname2url(uri), "", "", ""))

        scheme, netloc, path, params, query, fragment = \
            urlparse.urlparse(uri, "file", allow_fragments=0)
        scheme = scheme.lower()

        if scheme == "file":
                # During urlunparsing below, ensure that the path starts with
                # only one '/' character, if any are present.
                if path.startswith("/"):
                        path = "/" + path.lstrip("/")

        # Rebuild the URI with the sanitized components.
        return urlparse.urlunparse((scheme, netloc, path, params,
            query, fragment))


def makedirs(pathname):
        """Create a directory at the specified location if it does not
        already exist (including any parent directories) re-raising any
        unexpected exceptions as ApiExceptions.
        """

        try:
                os.makedirs(pathname, PKG_DIR_MODE)
        except EnvironmentError, e:
                if e.filename == pathname and (e.errno == errno.EEXIST or
                    os.path.exists(e.filename)):
                        return
                elif e.errno == errno.EACCES:
                        raise api_errors.PermissionsException(
                            e.filename)
                elif e.errno == errno.EROFS:
                        raise api_errors.ReadOnlyFileSystemException(
                            e.filename)
                elif e.errno != errno.EEXIST or e.filename != pathname:
                        raise

class DummyLock(object):
        """This has the same external interface as threading.Lock,
        but performs no locking.  This is a placeholder object for situations
        where we want to be able to do locking, but don't always need a
        lock object present.  The object has a held value, that is used
        for _is_owned.  This is informational and doesn't actually
        provide mutual exclusion in any way whatsoever."""

        def __init__(self):
                self.held = False

        def acquire(self, blocking=1):
                self.held = True
                return True

        def release(self):
                self.held = False
                return

        def _is_owned(self):
                return self.held

        @property
        def locked(self):
                return self.held


class Singleton(type):
        """Set __metaclass__ to Singleton to create a singleton.
        See http://en.wikipedia.org/wiki/Singleton_pattern """

        def __init__(self, name, bases, dictionary):
                super(Singleton, self).__init__(name, bases, dictionary)
                self.instance = None

        def __call__(self, *args, **kw):
                if self.instance is None:
                        self.instance = super(Singleton, self).__call__(*args,
                            **kw)

                return self.instance


EmptyDict = ImmutableDict()

# Setting the python file buffer size to 128k gives substantial performance
# gains on certain files.
PKG_FILE_BUFSIZ = 128 * 1024

PKG_FILE_MODE = stat.S_IWUSR | stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH
PKG_DIR_MODE = (stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH |
    stat.S_IXOTH)
PKG_RO_FILE_MODE = stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH

def relpath(path, start="."):
        """Version of relpath to workaround python bug:
            http://bugs.python.org/issue5117
        """
        if path and start and start == "/" and path[0] == "/":
                return path.lstrip("/")
        return os.path.relpath(path, start=start)

def recursive_chown_dir(d, uid, gid):
        """Change the ownership of all files under directory d to uid:gid."""
        for dirpath, dirnames, filenames in os.walk(d):
                for name in dirnames:
                        path = os.path.join(dirpath, name)
                        portable.chown(path, uid, gid)
                for name in filenames:
                        path = os.path.join(dirpath, name)
                        portable.chown(path, uid, gid)
def opts_parse(op, api_inst, args, table, pargs_limit, usage_cb):
        """Generic table-based options parsing function.  Returns a tuple
        consisting of a dictionary of parsed options and the remaining
        unparsed options.

        'op' is the operation being performed.

        'api_inst' is an image api object that is passed to options handling
        callbacks (passed in via 'table').

        'args' is the arguments that should be parsed.

        'table' is a list of options and callbacks.Each entry is either a
        a tuple or a callback function.

        tuples in 'table' specify allowable options and have the following
        format:

                (<short opt>, <long opt>, <key>, <default value>)

        An example of a short opt is "f", which maps to a "-f" option.  An
        example of a long opt is "foo", which maps to a "--foo" option.  Key
        is the value of this option in the parsed option dictionary.  The
        default value not only represents the default value assigned to the
        option, but it also implicitly determines how the option is parsed.  If
        the default value is True or False, the option doesn't take any
        arguments, can only be specified once, and if specified it inverts the
        default value.  If the default value is 0, the option doesn't take any
        arguments, can be specified multiple times, and if specified its value
        will be the number of times it was seen.  If the default value is
        None, the option requires an argument, can only be specified once, and
        if specified its value will be its argument string.  If the default
        value is an empty list, the option requires an argument, may be
        specified multiple times, and if specified its value will be a list
        with all the specified argument values.

        callbacks in 'table' specify callback functions that are invoked after
        all options have been parsed.  Callback functions must have the
        following signature:
                callback(api_inst, opts, opts_new)

        The opts parameter is a dictionary containing all the raw, parsed
        options.  Callbacks should never update the contents of this
        dictionary.  The opts_new parameter is a dictionary which is initially
        a copy of the opts dictionary.  This is the dictionary that will be
        returned to the caller of opts_parse().  If a callback function wants
        to update the arguments dictionary that will be returned to the
        caller, they should make all their updates to the opts_new dictionary.

        'pargs_limit' specified how to handle extra arguments not parsed by
        getops.  A value of -1 indicates that we allow an unlimited number of
        extra arguments.  A value of 0 or greater indicates the number of
        allowed additional unparsed options.

        'usage_cb' is a function pointer that should display usage information
        and will be invoked if invalid arguments are detected."""


        assert type(table) == list

        # return dictionary
        rv = dict()

        # option string passed to getopt
        opts_s_str = ""
        # long options list passed to getopt
        opts_l_list = list()

        # dict to map options returned by getopt to keys
        opts_keys = dict()

        # sanity checking to make sure each option is unique
        opts_s_set = set()
        opts_l_set = set()
        opts_seen = dict()

        # callbacks to invoke after processing options
        callbacks = []

        # process each option entry
        for entry in table:
                # check for a callback
                if type(entry) != tuple:
                        callbacks.append(entry)
                        continue

                # decode the table entry
                # s: a short option, ex: -f
                # l: a long option, ex: --foo
                # k: the key value for the options dictionary
                # v: the default value
                (s, l, k, v) = entry

                # make sure an option was specified
                assert s or l
                # sanity check the default value
                assert (v == None) or (v == []) or \
                    (type(v) == bool) or (type(v) == int)
                # make sure each key is unique
                assert k not in rv
                # initialize the default return dictionary entry.
                rv[k] = v
                if l:
                        # make sure each option is unique
                        assert set([l]) not in opts_l_set
                        opts_l_set |= set([l])

                        if type(v) == bool:
                                v = not v
                                opts_l_list.append("%s" % l)
                        elif type(v) == int:
                                opts_l_list.append("%s" % l)
                        else:
                                opts_l_list.append("%s=" % l)
                        opts_keys["--%s" % l] = k
                if s:
                        # make sure each option is unique
                        assert set([s]) not in opts_s_set
                        opts_s_set |= set([s])

                        if type(v) == bool:
                                v = not v
                                opts_s_str += "%s" % s
                        elif type(v) == int:
                                opts_s_str += "%s" % s
                        else:
                                opts_s_str += "%s:" % s
                        opts_keys["-%s" % s] = k

        # parse options
        try:
                opts, pargs = getopt.getopt(args, opts_s_str, opts_l_list)
        except getopt.GetoptError, e:
                usage_cb(_("illegal option -- %s") % e.opt, cmd=op)

        if (pargs_limit >= 0) and (pargs_limit < len(pargs)):
                usage_cb(_("illegal argument -- %s") % pargs[pargs_limit],
                    cmd=op)

        # update options dictionary with the specified options
        for opt, arg in opts:
                k = opts_keys[opt]
                v = rv[k]

                # check for duplicate options
                if k in opts_seen and (type(v) != list and type(v) != int):
                        if opt == opts_seen[k]:
                                usage_cb(_("option '%s' repeated") % opt,
                                    cmd=op)
                        usage_cb(_("'%s' and '%s' have the same meaning") %
                            (opts_seen[k], opt), cmd=op)
                opts_seen[k] = opt

                # update the return dict value
                if type(v) == bool:
                        rv[k] = not rv[k]
                elif type(v) == list:
                        rv[k].append(arg)
                elif type(v) == int:
                        rv[k] += 1
                else:
                        rv[k] = arg

        # invoke callbacks (cast to set() to eliminate dups)
        rv_updated = rv.copy()
        for cb in set(callbacks):
                cb(op, api_inst, rv, rv_updated)

        return (rv_updated, pargs)

def api_cmdpath():
        """Returns the path to the executable that is invoking the api client
        interfaces."""

        cmdpath = None

        if global_settings.client_args[0]:
                cmdpath = os.path.realpath(os.path.join(sys.path[0],
                    os.path.basename(global_settings.client_args[0])))

        if "PKG_CMDPATH" in os.environ:
                cmdpath = os.environ["PKG_CMDPATH"]

        if DebugValues.get_value("simulate_cmdpath"):
                cmdpath = DebugValues.get_value("simulate_cmdpath")

        return cmdpath

def liveroot():
        """Return path to the current live root image, i.e. the image
        that we are running from."""

        live_root = DebugValues.get_value("simulate_live_root")
        if not live_root and "PKG_LIVE_ROOT" in os.environ:
                live_root = os.environ["PKG_LIVE_ROOT"]
        if not live_root:
                live_root = "/"
        return live_root

def spaceavail(path):
        """Find out how much space is available at the specified path if
        it exists; return -1 if path doesn't exist"""
        try:
                res = os.statvfs(path)
                return res.f_frsize * res.f_bavail
        except OSError:
                return -1

def get_dir_size(path):
        """Return the size (in bytes) of a directory and all of its contents."""
        try:
                return sum(
                    os.path.getsize(os.path.join(d, fname))
                    for d, dnames, fnames in os.walk(path)
                    for fname in fnames
                )
        except EnvironmentError, e:
                raise api_errors._convert_error(e)

def get_listing(desired_field_order, field_data, field_values, out_format,
    def_fmt, omit_headers, escape_output=True):
        """Returns a string containing a listing defined by provided values
        in the specified output format.

        'desired_field_order' is the list of the fields to show in the order
        they should be output left to right.

        'field_data' is a dictionary of lists of the form:
          {
            field_name1: {
              [(output formats), field header, initial field value]
            },
            field_nameN: {
              [(output formats), field header, initial field value]
            }
          }

        'field_values' is a generator or list of dictionaries of the form:
          {
            field_name1: field_value,
            field_nameN: field_value
          }

        'out_format' is the format to use for output.  Currently 'default',
        'tsv', 'json', and 'json-formatted' are supported.  The first is
        intended for columnar, human-readable output, and the others for
        parsable output.

        'def_fmt' is the default Python formatting string to use for the
        'default' human-readable output.  It must match the fields defined
        in 'field_data'.

        'omit_headers' is a boolean specifying whether headers should be
        included in the listing.  (If applicable to the specified output
        format.)

        'escape_output' is an optional boolean indicating whether shell
        metacharacters or embedded control sequences should be escaped
        before display.  (If applicable to the specified output format.)
        """

        # Custom sort function for preserving field ordering
        def sort_fields(one, two):
                return desired_field_order.index(get_header(one)) - \
                    desired_field_order.index(get_header(two))

        # Functions for manipulating field_data records
        def filter_default(record):
                return "default" in record[0]

        def filter_tsv(record):
                return "tsv" in record[0]

        def get_header(record):
                return record[1]

        def get_value(record):
                return record[2]

        def quote_value(val):
                if out_format == "tsv":
                        # Expand tabs if tsv output requested.
                        val = val.replace("\t", " " * 8)
                nval = val
                # Escape bourne shell metacharacters.
                for c in ("\\", " ", "\t", "\n", "'", "`", ";", "&", "(", ")",
                    "|", "^", "<", ">"):
                        nval = nval.replace(c, "\\" + c)
                return nval

        def set_value(entry):
                val = entry[1]
                multi_value = False
                if isinstance(val, (list, tuple, set, frozenset)):
                        multi_value = True
                elif val == "":
                        entry[0][2] = '""'
                        return
                elif val is None:
                        entry[0][2] = ''
                        return
                else:
                        val = [val]

                nval = []
                for v in val:
                        if v == "":
                                # Indicate empty string value using "".
                                nval.append('""')
                        elif v is None:
                                # Indicate no value using empty string.
                                nval.append('')
                        elif escape_output:
                                # Otherwise, escape the value to be displayed.
                                nval.append(quote_value(str(v)))
                        else:
                                # Caller requested value not be escaped.
                                nval.append(str(v))

                val = " ".join(nval)
                nval = None
                if multi_value:
                        val = "(%s)" % val
                entry[0][2] = val

        if out_format == "default":
                # Create a formatting string for the default output
                # format.
                fmt = def_fmt
                filter_func = filter_default
        elif out_format == "tsv":
                # Create a formatting string for the tsv output
                # format.
                num_fields = sum(
                    1 for k in field_data
                    if filter_tsv(field_data[k])
                )
                fmt = "\t".join('%s' for x in xrange(num_fields))
                filter_func = filter_tsv
        elif out_format == "json" or out_format == "json-formatted":
                args = { "sort_keys": True }
                if out_format == "json-formatted":
                        args["indent"] = 2

                # 'json' formats always include any extra fields returned;
                # any explicitly named fields are only included if 'json'
                # is explicitly listed.
                def fmt_val(v):
                        if isinstance(v, basestring):
                                return v
                        if isinstance(v, (list, tuple, set, frozenset)):
                                return [fmt_val(e) for e in v]
                        if isinstance(v, dict):
                                for k, e in v.items():
                                        v[k] = fmt_val(e)
                                return v
                        return str(v)

                output = json.dumps([
                    dict(
                        (k, fmt_val(entry[k]))
                        for k in entry
                        if k not in field_data or "json" in field_data[k][0]
                    )
                    for entry in field_values
                ], **args)

                if out_format == "json-formatted":
                        # Include a trailing newline for readability.
                        return output + "\n"
                return output

        # Extract the list of headers from the field_data dictionary.  Ensure
        # they are extracted in the desired order by using the custom sort
        # function.
        hdrs = map(get_header, sorted(filter(filter_func, field_data.values()),
            sort_fields))

        # Output a header if desired.
        output = ""
        if not omit_headers:
                output += fmt % tuple(hdrs)
                output += "\n"

        for entry in field_values:
                map(set_value, (
                    (field_data[f], v)
                    for f, v in entry.iteritems()
                    if f in field_data
                ))
                values = map(get_value, sorted(filter(filter_func,
                    field_data.values()), sort_fields))
                output += fmt % tuple(values)
                output += "\n"

        return output
