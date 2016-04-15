#!/usr/bin/python
#
# Copyright (C) 2002 Lars Gustaebel <lars@gustaebel.de>
# All rights reserved.
#
# Permission  is  hereby granted,  free  of charge,  to  any person
# obtaining a  copy of  this software  and associated documentation
# files  (the  "Software"),  to   deal  in  the  Software   without
# restriction,  including  without limitation  the  rights to  use,
# copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies  of  the  Software,  and to  permit  persons  to  whom the
# Software  is  furnished  to  do  so,  subject  to  the  following
# conditions:
#
# The above copyright  notice and this  permission notice shall  be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS  IS", WITHOUT WARRANTY OF ANY  KIND,
# EXPRESS OR IMPLIED, INCLUDING  BUT NOT LIMITED TO  THE WARRANTIES
# OF  MERCHANTABILITY,  FITNESS   FOR  A  PARTICULAR   PURPOSE  AND
# NONINFRINGEMENT.  IN  NO  EVENT SHALL  THE  AUTHORS  OR COPYRIGHT
# HOLDERS  BE LIABLE  FOR ANY  CLAIM, DAMAGES  OR OTHER  LIABILITY,
# WHETHER  IN AN  ACTION OF  CONTRACT, TORT  OR OTHERWISE,  ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.
#
"""Read from and write to cpio format archives.
"""

#
# Copyright (c) 2008, 2016, Oracle and/or its affiliates. All rights reserved.
#

from __future__ import print_function

#---------
# Imports
#---------
import sys
if sys.version > '3':
        long = int
import os
import stat
import time
import struct
from six.moves import range
import pkg.pkgsubprocess as subprocess

# cpio magic numbers
# XXX matches actual cpio archives and /etc/magic, but not archives.h
CMN_ASC = 0o70701        # Cpio Magic Number for ASCII header
CMN_BIN = 0o70707        # Cpio Magic Number for Binary header
CMN_BBS = 0o143561       # Cpio Magic Number for Byte-Swap header
CMN_CRC = 0o70702        # Cpio Magic Number for CRC header
CMS_ASC = "070701"       # Cpio Magic String for ASCII header
CMS_CHR = "070707"       # Cpio Magic String for CHR (-c) header
CMS_CRC = "070702"       # Cpio Magic String for CRC header
CMS_LEN = 6              # Cpio Magic String length

BLOCKSIZE = 512

class CpioError(Exception):
        """Base exception."""
        pass
class ExtractError(CpioError):
        """General exception for extract errors."""
        pass
class ReadError(CpioError):
        """Exception for unreadble cpio archives."""
        pass
class CompressionError(CpioError):
        """Exception for unavailable compression methods."""
        pass
class StreamError(CpioError):
        """Exception for unsupported operations on stream-like CpioFiles."""
        pass

#---------------------------
# internal stream interface
#---------------------------
class _LowLevelFile:
        """Low-level file object. Supports reading and writing.
        It is used instead of a regular file object for streaming
        access.
        """

        def __init__(self, name, mode):
                mode = {
                        "r": os.O_RDONLY,
            "w": os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                }[mode]
                if hasattr(os, "O_BINARY"):
                        mode |= os.O_BINARY
                self.fd = os.open(name, mode)

        def close(self):
                os.close(self.fd)

        def read(self, size):
                return os.read(self.fd, size)

        def write(self, s):
                os.write(self.fd, s)

class _Stream:
        """Class that serves as an adapter between CpioFile and
        a stream-like object.  The stream-like object only
        needs to have a read() or write() method and is accessed
        blockwise.  Use of gzip or bzip2 compression is possible.
        A stream-like object could be for example: sys.stdin,
        sys.stdout, a socket, a tape device etc.

        _Stream is intended to be used only internally.
        """

        def __init__(self, name, mode, type, fileobj, bufsize):
                """Construct a _Stream object.
                """
                self._extfileobj = True
                if fileobj is None:
                        fileobj = _LowLevelFile(name, mode)
                        self._extfileobj = False

                self.name = name or ""
                self.mode = mode
                self.type = type
                self.fileobj = fileobj
                self.bufsize = bufsize
                self.buf = ""
                self.pos = long(0)
                self.closed = False

                if type == "gz":
                        try:
                                import zlib
                        except ImportError:
                                raise CompressionError("zlib module is not available")
                        self.zlib = zlib
                        self.crc = zlib.crc32("")
                        if mode == "r":
                                self._init_read_gz()
                        else:
                                self._init_write_gz()

                if type == "bz2":
                        try:
                                import bz2
                        except ImportError:
                                raise CompressionError("bz2 module is not available")
                        if mode == "r":
                                self.dbuf = ""
                                self.cmp = bz2.BZ2Decompressor()
                        else:
                                self.cmp = bz2.BZ2Compressor()

        def __del__(self):
                if not self.closed:
                        self.close()

        def _init_write_gz(self):
                """Initialize for writing with gzip compression.
                """
                self.cmp = self.zlib.compressobj(9, self.zlib.DEFLATED,
                        -self.zlib.MAX_WBITS, self.zlib.DEF_MEM_LEVEL, 0)
                timestamp = struct.pack("<L", long(time.time()))
                self.__write("\037\213\010\010{0}\002\377".format(timestamp))
                if self.name.endswith(".gz"):
                        self.name = self.name[:-3]
                self.__write(self.name + NUL)

        def write(self, s):
                """Write string s to the stream.
                """
                if self.type == "gz":
                        self.crc = self.zlib.crc32(s, self.crc)
                self.pos += len(s)
                if self.type != "cpio":
                        s = self.cmp.compress(s)
                self.__write(s)

        def __write(self, s):
                """Write string s to the stream if a whole new block
                is ready to be written.
                """
                self.buf += s
                while len(self.buf) > self.bufsize:
                        self.fileobj.write(self.buf[:self.bufsize])
                        self.buf = self.buf[self.bufsize:]

        def close(self):
                """Close the _Stream object.  No operation should be
                done on it afterwards.
                """
                if self.closed:
                        return

                if self.mode == "w" and self.type != "cpio":
                        self.buf += self.cmp.flush()
                if self.mode == "w" and self.buf:
                        self.fileobj.write(self.buf)
                        self.buf = ""
                        if self.type == "gz":
                                self.fileobj.write(struct.pack("<l", self.crc))
                                self.fileobj.write(struct.pack("<L", self.pos &
                                    long(0xffffFFFF)))
                if not self._extfileobj:
                        self.fileobj.close()

                self.closed = True

        def _init_read_gz(self):
                """Initialize for reading a gzip compressed fileobj.
                """
                self.cmp = self.zlib.decompressobj(-self.zlib.MAX_WBITS)
                self.dbuf = ""

                # taken from gzip.GzipFile with some alterations
                if self.__read(2) != "\037\213":
                        raise ReadError("not a gzip file")
                if self.__read(1) != "\010":
                        raise CompressionError("unsupported compression method")

                flag = ord(self.__read(1))
                self.__read(6)

                if flag & 4:
                        xlen = ord(self.__read(1)) + 256 * ord(self.__read(1))
                        self.read(xlen)
                if flag & 8:
                        while True:
                                s = self.__read(1)
                                if not s or s == NUL:
                                        break
                if flag & 16:
                        while True:
                                s = self.__read(1)
                                if not s or s == NUL:
                                        break
                if flag & 2:
                        self._read(2)

        def tell(self):
                """Return the stream's file pointer position.
                """
                return self.pos

        def seek(self, pos=0):
                """Set the stream's file pointer to pos. Negative seeking
                is forbidden.
                """
                if pos - self.pos >= 0:
                        blocks, remainder = divmod(pos - self.pos, self.bufsize)
                        for i in range(blocks):
                                self.read(self.bufsize)
                        self.read(remainder)
                else:
                        raise StreamError("seeking backwards is not allowed")
                return self.pos

        def read(self, size=None):
                """Return the next size number of bytes from the stream.
                If size is not defined, return all bytes of the stream
                up to EOF.
                """
                if size is None:
                        t = []
                        while True:
                                buf = self._read(self.bufsize)
                                if not buf:
                                        break
                                t.append(buf)
                        buf = "".join(t)
                else:
                        buf = self._read(size)
                self.pos += len(buf)
                # print("reading {0} bytes to {1} ({2})".format(size, self.pos, self.fileobj.tell()))
                return buf

        def _read(self, size):
                """Return size bytes from the stream.
                """
                if self.type == "cpio":
                        return self.__read(size)

                c = len(self.dbuf)
                t = [self.dbuf]
                while c < size:
                        buf = self.__read(self.bufsize)
                        if not buf:
                                break
                        buf = self.cmp.decompress(buf)
                        t.append(buf)
                        c += len(buf)
                t = "".join(t)
                self.dbuf = t[size:]
                return t[:size]

        def __read(self, size):
                """Return size bytes from stream. If internal buffer is empty,
                read another block from the stream.
                """
                c = len(self.buf)
                t = [self.buf]
                while c < size:
                        buf = self.fileobj.read(self.bufsize)
                        if not buf:
                                break
                        t.append(buf)
                        c += len(buf)
                t = "".join(t)
                self.buf = t[size:]
                return t[:size]
# class _Stream

#------------------------
# Extraction file object
#------------------------
class ExFileObject(object):
        """File-like object for reading an archive member.
           Is returned by CpioFile.extractfile().
        """

        def __init__(self, cpiofile, cpioinfo):
                self.fileobj    = cpiofile.fileobj
                self.name       = cpioinfo.name
                self.mode       = "r"
                self.closed     = False
                self.offset     = cpioinfo.offset_data
                self.size       = cpioinfo.size
                self.pos        = long(0)
                self.linebuffer = ""

        def read(self, size=None):
                if self.closed:
                        raise ValueError("file is closed")
                self.fileobj.seek(self.offset + self.pos)
                bytesleft = self.size - self.pos
                if size is None:
                        bytestoread = bytesleft
                else:
                        bytestoread = min(size, bytesleft)
                self.pos += bytestoread
                return self.fileobj.read(bytestoread)

        def readline(self, size=-1):
                """Read a line with approx. size. If size is negative,
                read a whole line. readline() and read() must not
                be mixed up (!).
                """
                if size < 0:
                        size = sys.maxsize

                nl = self.linebuffer.find("\n")
                if nl >= 0:
                        nl = min(nl, size)
                else:
                        size -= len(self.linebuffer)
                        while (nl < 0 and size > 0):
                                buf = self.read(min(size, 100))
                                if not buf:
                                        break
                                self.linebuffer += buf
                                size -= len(buf)
                                nl = self.linebuffer.find("\n")
                        if nl == -1:
                                s = self.linebuffer
                                self.linebuffer = ""
                                return s
                buf = self.linebuffer[:nl]
                self.linebuffer = self.linebuffer[nl + 1:]
                while buf[-1:] == "\r":
                        buf = buf[:-1]
                return buf + "\n"

        def readlines(self):
                """Return a list with all (following) lines.
                """
                result = []
                while True:
                        line = self.readline()
                        if not line: break
                        result.append(line)
                return result

        def tell(self):
                """Return the current file position.
                """
                return self.pos

        def seek(self, pos, whence=0):
                """Seek to a position in the file.
                """
                self.linebuffer = ""
                if whence == 0:
                        self.pos = min(max(pos, 0), self.size)
                elif whence == 1:
                        if pos < 0:
                                self.pos = max(self.pos + pos, 0)
                        else:
                                self.pos = min(self.pos + pos, self.size)
                elif whence == 2:
                        self.pos = max(min(self.size + pos, self.size), 0)

        def close(self):
                """Close the file object.
                """
                self.closed = True
#class ExFileObject

#------------------
# Exported Classes
#------------------
class CpioInfo(object):
        """Informational class which holds the details about an
        archive member given by a cpio header block.
        CpioInfo objects are returned by CpioFile.getmember(),
        CpioFile.getmembers() and CpioFile.getcpioinfo() and are
        usually created internally.
        """

        def __init__(self, name="", cpiofile=None):
                """Construct a CpioInfo object. name is the optional name
                of the member.
                """

                self.name       = name
                self.mode       = 0o666
                self.uid        = 0
                self.gid        = 0
                self.size       = 0
                self.mtime      = 0
                self.chksum     = 0
                self.type       = "0"
                self.linkname   = ""
                self.uname      = "user"
                self.gname      = "group"
                self.devmajor   = 0
                self.devminor   = 0
                self.prefix     = ""
                self.cpiofile   = cpiofile

                self.offset     = 0
                self.offset_data = 0
                self.padding    = 1

        def __repr__(self):
                return "<{0} {1!r} at {2:#x}>".format(
                    self.__class__.__name__, self.name, id(self))

        @classmethod
        def frombuf(cls, buf, fileobj, cpiofile=None):
                """Construct a CpioInfo object from a buffer.  The buffer should
                be at least 6 octets long to determine the type of archive.  The
                rest of the data will be read in on demand.
                """
                cpioinfo = cls(cpiofile=cpiofile)

                # Read enough for the ASCII magic
                if buf[:6] == CMS_ASC:
                        hdrtype = "CMS_ASC"
                elif buf[:6] == CMS_CHR:
                        hdrtype = "CMS_CHR"
                elif buf[:6] == CMS_CRC:
                        hdrtype = "CMS_CRC"
                else:
                        b = struct.unpack("h", buf[:2])[0]
                        if b == CMN_ASC:
                                hdrtype = "CMN_ASC"
                        elif b == CMN_BIN:
                                hdrtype = "CMN_BIN"
                        elif b == CMN_BBS:
                                hdrtype = "CMN_BBS"
                        elif b == CMN_CRC:
                                hdrtype = "CMN_CRC"
                        else:
                                raise ValueError("invalid cpio header")

                if hdrtype == "CMN_BIN":
                        buf += fileobj.read(26 - len(buf))
                        (magic, dev, inode, cpioinfo.mode, cpioinfo.uid,
                        cpioinfo.gid, nlink, rdev, cpioinfo.mtime, namesize,
                        cpioinfo.size) = struct.unpack("=hhHHHHhhihi", buf[:26])
                        buf += fileobj.read(namesize)
                        cpioinfo.name = buf[26:26 + namesize - 1]
                        # Header is padded to halfword boundaries
                        cpioinfo.padding = 2
                        cpioinfo.hdrsize = 26 + namesize + (namesize % 2)
                        buf += fileobj.read(namesize % 2)
                elif hdrtype == "CMS_ASC":
                        buf += fileobj.read(110 - len(buf))
                        cpioinfo.mode = int(buf[14:22], 16)
                        cpioinfo.uid  = int(buf[22:30], 16)
                        cpioinfo.gid  = int(buf[30:38], 16)
                        cpioinfo.mtime = int(buf[46:54], 16)
                        cpioinfo.size = int(buf[54:62], 16)
                        cpioinfo.devmajor = int(buf[62:70], 16)
                        cpioinfo.devminor = int(buf[70:78], 16)
                        namesize = int(buf[94:102], 16)
                        cpioinfo.chksum = int(buf[102:110], 16)
                        buf += fileobj.read(namesize)
                        cpioinfo.name = buf[110:110 + namesize - 1]
                        cpioinfo.hdrsize = 110 + namesize
                        # Pad to the nearest 4 byte block, 0-3 bytes.
                        cpioinfo.hdrsize += 4 - ((cpioinfo.hdrsize - 1) % 4) - 1
                        buf += fileobj.read(cpioinfo.hdrsize - 110 - namesize)
                        cpioinfo.padding = 4
                else:
                        raise ValueError("unsupported cpio header")

                return cpioinfo

        def isreg(self):
                return stat.S_ISREG(self.mode)

        # This isn't in tarfile, but it's too useful.  It's required
        # modifications to frombuf(), as well as CpioFile.next() to pass the
        # CpioFile object in.  I'm not sure that isn't poor OO style.
        def extractfile(self):
                """Return a file-like object which can be read to extract the contents.
                """

                if self.isreg():
                        return ExFileObject(self.cpiofile, self)
                else:
                        return None

class CpioFile(object):
        """The CpioFile Class provides an interface to cpio archives.
        """

        fileobject = ExFileObject

        def __init__(self, name=None, mode="r", fileobj=None, cfobj=None):
                """Open an (uncompressed) cpio archive `name'. `mode' is either 'r' to
                read from an existing archive, 'a' to append data to an existing
                file or 'w' to create a new file overwriting an existing one.  `mode'
                defaults to 'r'.
                If  `fileobj' is given, it is used for reading or writing data.  If it
                can be determined, `mode' is overridden by `fileobj's mode.
                `fileobj' is not closed, when CpioFile is closed.
                """
                self.name = name

                if len(mode) > 1 or mode not in "raw":
                        raise ValueError("mode must be 'r', 'a' or 'w'")
                self._mode = mode
                self.mode = {"r": "rb", "a": "r+b", "w": "wb"}[mode]

                if not fileobj and not cfobj:
                        fileobj = open(self.name, self.mode)
                        self._extfileobj = False
                else:
                        # Copy constructor: just copy fileobj over and reset the
                        # _Stream object's idea of where we are back to the
                        # beginning.  Everything else will be reset normally.
                        # XXX clear closed flag?
                        if cfobj:
                                fileobj = cfobj.fileobj
                                fileobj.pos = 0
                        if self.name is None and hasattr(fileobj, "name"):
                                self.name = fileobj.name
                        if hasattr(fileobj, "mode"):
                                self.mode = fileobj.mode
                        self._extfileobj = True
                self.fileobj = fileobj

                # Init datastructures
                self.closed     = False
                self.members    = []    # list of members as CpioInfo objects
                self._loaded    = False # flag if all members have been read
                self.offset     = long(0)    # current position in the archive file

                if self._mode == "r":
                        self.firstmember = None
                        self.firstmember = next(self)

                if self._mode == "a":
                        # Move to the end of the archive,
                        # before the first empty block.
                        self.firstmember = None
                        while True:
                                try:
                                        cpioinfo = next(self)
                                except ReadError:
                                        self.fileobj.seek(0)
                                        break
                                if cpioinfo is None:
                                        self.fileobj.seek(- BLOCKSIZE, 1)
                                        break

                if self._mode in "aw":
                        self._loaded = True

        #--------------------------------------------------------------------------
        # Below are the classmethods which act as alternate constructors to the
        # CpioFile class. The open() method is the only one that is needed for
        # public use; it is the "super"-constructor and is able to select an
        # adequate "sub"-constructor for a particular compression using the mapping
        # from OPEN_METH.
        #
        # This concept allows one to subclass CpioFile without losing the comfort of
        # the super-constructor. A sub-constructor is registered and made available
        # by adding it to the mapping in OPEN_METH.
        @classmethod
        def open(cls, name=None, mode="r", fileobj=None, bufsize=20*512):
                """Open a cpio archive for reading, writing or appending. Return
                an appropriate CpioFile class.

                mode:
                'r'             open for reading with transparent compression
                'r:'            open for reading exclusively uncompressed
                'r:gz'          open for reading with gzip compression
                'r:bz2'         open for reading with bzip2 compression
                'a' or 'a:'     open for appending
                'w' or 'w:'     open for writing without compression
                'w:gz'          open for writing with gzip compression
                'w:bz2'         open for writing with bzip2 compression
                'r|'            open an uncompressed stream of cpio blocks for reading
                'r|gz'          open a gzip compressed stream of cpio blocks
                'r|bz2'         open a bzip2 compressed stream of cpio blocks
                'w|'            open an uncompressed stream for writing
                'w|gz'          open a gzip compressed stream for writing
                'w|bz2'         open a bzip2 compressed stream for writing
                """

                if not name and not fileobj:
                        raise ValueError("nothing to open")

                if ":" in mode:
                        filemode, comptype = mode.split(":", 1)
                        filemode = filemode or "r"
                        comptype = comptype or "cpio"

                        # Select the *open() function according to
                        # given compression.
                        if comptype in cls.OPEN_METH:
                                func = getattr(cls, cls.OPEN_METH[comptype])
                        else:
                                raise CompressionError("unknown compression type {0!r}".format(comptype))
                        return func(name, filemode, fileobj)

                elif "|" in mode:
                        filemode, comptype = mode.split("|", 1)
                        filemode = filemode or "r"
                        comptype = comptype or "cpio"

                        if filemode not in "rw":
                                raise ValueError("mode must be 'r' or 'w'")

                        t = cls(name, filemode,
                                _Stream(name, filemode, comptype, fileobj, bufsize))
                        t._extfileobj = False
                        return t

                elif mode == "r":
                        # Find out which *open() is appropriate for opening the file.
                        for comptype in cls.OPEN_METH:
                                func = getattr(cls, cls.OPEN_METH[comptype])
                                try:
                                        return func(name, "r", fileobj)
                                except (ReadError, CompressionError):
                                        continue
                        raise ReadError("file could not be opened successfully")

                elif mode in "aw":
                        return cls.cpioopen(name, mode, fileobj)

                raise ValueError("undiscernible mode")

        @classmethod
        def cpioopen(cls, name, mode="r", fileobj=None):
                """Open uncompressed cpio archive name for reading or writing.
                """
                if len(mode) > 1 or mode not in "raw":
                        raise ValueError("mode must be 'r', 'a' or 'w'")
                return cls(name, mode, fileobj)

        @classmethod
        def gzopen(cls, name, mode="r", fileobj=None, compresslevel=9):
                """Open gzip compressed cpio archive name for reading or writing.
                Appending is not allowed.
                """
                if len(mode) > 1 or mode not in "rw":
                        raise ValueError("mode must be 'r' or 'w'")

                try:
                        import gzip
                        gzip.GzipFile
                except (ImportError, AttributeError):
                        raise CompressionError("gzip module is not available")

                pre, ext = os.path.splitext(name)
                pre = os.path.basename(pre)
                if ext == ".gz":
                        ext = ""
                cpioname = pre + ext

                if fileobj is None:
                        fileobj = open(name, mode + "b")

                if mode != "r":
                        name = tarname

                try:
                        t = cls.cpioopen(cpioname, mode,
                                gzip.GzipFile(name, mode, compresslevel,
                                        fileobj))
                except IOError:
                        raise ReadError("not a gzip file")
                t._extfileobj = False
                return t

        @classmethod
        def bz2open(cls, name, mode="r", fileobj=None, compresslevel=9):
                """Open bzip2 compressed cpio archive name for reading or writing.
                Appending is not allowed.
                """
                if len(mode) > 1 or mode not in "rw":
                        raise ValueError("mode must be 'r' or 'w'.")

                try:
                        import bz2
                except ImportError:
                        raise CompressionError("bz2 module is not available")

                pre, ext = os.path.splitext(name)
                pre = os.path.basename(pre)
                if ext == ".bz2":
                        ext = ""
                cpioname = pre + ext

                if fileobj is not None:
                        raise ValueError("no support for external file objects")

                try:
                        t = cls.cpioopen(cpioname, mode,
                            bz2.BZ2File(name, mode, compresslevel=compresslevel))
                except IOError:
                        raise ReadError("not a bzip2 file")
                t._extfileobj = False
                return t

        @classmethod
        def p7zopen(cls, name, mode="r", fileobj=None):
                """Open 7z compressed cpio archive name for reading, writing.

                Appending is not allowed
                """
                if len(mode) > 1 or mode not in "rw":
                        raise ValueError("mode must be 'r' or 'w'.")

                pre, ext = os.path.splitext(name)
                pre = os.path.basename(pre)
                if ext == ".7z":
                        ext = ""
                cpioname = pre + ext

                try:
                        # To extract: 7z e -so <fname>
                        # To create an archive: 7z a -si <fname>
                        cmd = "7z {0} -{1} {2}".format(
                            {'r':'e',  'w':'a'}[mode],
                            {'r':'so', 'w':'si'}[mode],
                            name)
                        p = subprocess.Popen(cmd.split(),
                            stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
                        pobj = p.stdout
                        if mode == "w":
                                pobj = p.stdin

                        comptype = "cpio"
                        bufsize = 20*512

                        obj = _Stream(cpioname, mode, comptype, pobj, bufsize)
                        t = cls.cpioopen(cpioname, mode, obj)
                except IOError:
                        raise ReadError("read/write via 7z failed")
                t._extfileobj = False
                return t

        # All *open() methods are registered here.
        OPEN_METH = {
                "cpio": "cpioopen",     # uncompressed
                "gz":   "gzopen",       # gzip compressed
                "bz2":  "bz2open",      # bzip2 compressed
                "p7z":  "p7zopen"       # 7z compressed
        }

        def getmember(self, name):
                """Return a CpioInfo object for member `name'. If `name' can not be
                found in the archive, KeyError is raised. If a member occurs more
                than once in the archive, its last occurence is assumed to be the
                most up-to-date version.
                """
                cpioinfo = self._getmember(name)
                if cpioinfo is None:
                        raise KeyError("filename {0!r} not found".format(name))
                return cpioinfo

        def getmembers(self):
                """Return the members of the archive as a list of CpioInfo objects. The
                list has the same order as the members in the archive.
                """
                self._check()
                if not self._loaded:    # if we want to obtain a list of
                        self._load()    # all members, we first have to
                                        # scan the whole archive.
                return self.members

        def __next__(self):
                self._check("ra")
                if self.firstmember is not None:
                        m = self.firstmember
                        self.firstmember = None
                        return m

                self.fileobj.seek(self.offset)
                while True:
                        # Read in enough for frombuf() to be able to determine
                        # what kind of archive it is.  It will have to read the
                        # rest of the header.
                        buf = self.fileobj.read(6)
                        if not buf:
                                return None
                        try:
                                cpioinfo = CpioInfo.frombuf(buf, self.fileobj, self)
                        except ValueError as e:
                                if self.offset == 0:
                                        raise ReadError("empty, unreadable or compressed file")
                                return None
                        break

                # if cpioinfo.chksum != calc_chksum(buf):
                #         self._dbg(1, "cpiofile: Bad Checksum {0!r}".format(cpioinfo.name))

                cpioinfo.offset = self.offset

                cpioinfo.offset_data = self.offset + cpioinfo.hdrsize
                if cpioinfo.isreg() or cpioinfo.type not in (0,): # XXX SUPPORTED_TYPES?
                        self.offset += cpioinfo.hdrsize + cpioinfo.size
                        if self.offset % cpioinfo.padding != 0:
                                self.offset += cpioinfo.padding - \
                                                (self.offset % cpioinfo.padding)

                if cpioinfo.name == "TRAILER!!!":
                        return None

                self.members.append(cpioinfo)
                return cpioinfo

        next = __next__

        def extractfile(self, member):
                self._check("r")

                if isinstance(member, CpioInfo):
                        cpioinfo = member
                else:
                        cpioinfo = self.getmember(member)

                if cpioinfo.isreg():
                        return self.fileobject(self, cpioinfo)
                # XXX deal with other types
                else:
                        return None

        def _block(self, count):
                blocks, remainder = divmod(count, BLOCKSIZE)
                if remainder:
                        blocks += 1
                return blocks * BLOCKSIZE

        def _getmember(self, name, cpioinfo=None):
                members = self.getmembers()

                if cpioinfo is None:
                        end = len(members)
                else:
                        end = members.index(cpioinfo)

                for i in range(end - 1, -1, -1):
                        if name == members[i].name:
                                return members[i]

        def _load(self):
                while True:
                        cpioinfo = next(self)
                        if cpioinfo is None:
                                break
                self._loaded = True

        def _check(self, mode=None):
                if self.closed:
                        raise IOError("{0} is closed".format(
                            self.__class__.__name__))
                if mode is not None and self._mode not in mode:
                        raise IOError("bad operation for mode {0!r}".format(
                            self._mode))

        def __iter__(self):
                if self._loaded:
                        return iter(self.members)
                else:
                        return CpioIter(self)

        def find_next_archive(self, padding=512):
                """Find the next cpio archive glommed on to the end of the current one.

                Some applications, like Solaris package datastreams, concatenate
                multiple cpio archives together, separated by a bit of padding.
                This routine puts all the file pointers in position to start
                reading from the next archive, which can be done by creating a
                new CpioFile object given the original one as an argument (after
                this routine is called).
                """

                bytes = 0
                if self.fileobj.tell() % padding != 0:
                        bytes = padding - self.fileobj.tell() % padding
                self.fileobj.seek(self.fileobj.tell() + bytes)
                self.offset += bytes

        def get_next_archive(self, padding=512):
                """Return the next cpio archive glommed on to the end of the current one.

                Return the CpioFile object based on the repositioning done by
                find_next_archive().
                """

                self.find_next_archive(padding)
                return CpioFile(cfobj=self)

class CpioIter:
        def __init__(self, cpiofile):
                self.cpiofile = cpiofile
                self.index = 0

        def __iter__(self):
                return self

        def __next__(self):
                if not self.cpiofile._loaded:
                        cpioinfo = next(self.cpiofile)
                        if not cpioinfo:
                                self.cpiofile._loaded = True
                                raise StopIteration
                else:
                        try:
                                cpioinfo = self.cpiofile.members[self.index]
                        except IndexError:
                                raise StopIteration
                self.index += 1
                return cpioinfo

        next = __next__

def is_cpiofile(name):

        magic = open(name).read(CMS_LEN)

        if magic in (CMS_ASC, CMS_CHR, CMS_CRC):
                return True
        elif struct.unpack("h", magic[:2])[0] in \
                (CMN_ASC, CMN_BIN, CMN_BBS, CMN_CRC):
                return True

        return False

if __name__ == "__main__":
        print(is_cpiofile(sys.argv[1]))

        cf = CpioFile.open(sys.argv[1])
        print("cpiofile is:", cf)

        for ci in cf:
                print("cpioinfo is:", ci)
                print("  mode:", oct(ci.mode))
                print("  uid:", ci.uid)
                print("  gid:", ci.gid)
                print("  mtime:", ci.mtime, "({0})".format(
                    time.ctime(ci.mtime)))
                print("  size:", ci.size)
                print("  name:", ci.name)
                # f = cf.extractfile(ci)
                # for l in f.readlines():
                #         print(l, end=" ")
                # f.close()
