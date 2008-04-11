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
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

"""module describing a generic packaging object

This module contains the Action class, which represents a generic packaging
object.  It also contains a helper function, gunzip_from_stream(), which actions
may use to decompress their data payloads."""

import os
import sha
import zlib
import errno

import pkg.actions
import pkg.portable as portable

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

        # 'name' is the name of the action, as specified in a manifest.
        name = "generic"
        # 'attributes' is a list of the known usable attributes.  Or something.
        # There probably isn't a good use for it.
        attributes = ()
        # 'key_attr' is the name of the attribute whose value must be unique in
        # the namespace of objects represented by a particular action.  For
        # instance, a file's key_attr would be its pathname.  Or a driver's
        # key_attr would be the driver name.  When 'key_attr' is None, it means
        # that all attributes of the action are distinguishing.
        key_attr = None

        # the following establishes the sort order between action types.
        # Directories must precede all
        # filesystem-modifying actions; hardlinks must follow all
        # filesystem-modifying actions.  Note that usr/group actions
        # preceed file actions; this implies that /etc/group and /etc/passwd
        # file ownership needs to be part of initial contents of those files

        orderdict = {}
        unknown = 0

        def loadorderdict(self):
                ol = [
                        "set",
                        "depend",
                        "group",
                        "user",
                        "dir",
                        "file",
                        "hardlink",
                        "link",
                        "driver",
                        "unknown",
                        "legacy"
                        ]
                self.orderdict.update(dict((
                    (pkg.actions.types[t], i) for i, t in enumerate(ol)
                    )))
                self.unknown = self.orderdict[pkg.actions.types["unknown"]]

        def __init__(self, data=None, **attrs):
                """Action constructor.

                The optional 'data' argument may be either a string, a file-like
                object, or a callable.  If it is a string, then it will be
                substituted with a callable that will return an open handle to
                the file represented by the string.  Otherwise, if it is not
                already a callable, it is assumed to be a file-like object, and
                will be substituted with a callable that will return the object.
                If it is a callable, it will not be replaced at all.

                For file-like 'data' arguments, The internal 'cleanup'
                attribute will be set to a callable which will delete the
                underlying file after the data is processed.

                Any remaining named arguments will be treated as attributes.
                """

                if not self.orderdict:
                        self.loadorderdict()
                self.ord = self.orderdict.get(type(self), self.unknown)

                self.attrs = attrs

                if data == None:
                        self.data = None
                        self.cleanup = None
                        return

                if isinstance(data, str):
                        def file_opener():
                                return open(data, "rb")
                        self.data = file_opener
                        def file_cleanup():
                                os.unlink(data)
                        self.cleanup = file_cleanup
                elif not callable(data):
                        def data_opener():
                                return data
                        self.data = data_opener
                        self.cleanup = None
                else:
                        # Data is not None, and is callable
                        self.data = data
                        self.cleanup = None

        def __str__(self):
                """Serialize the action into manifest form.

                The form is the name, followed by the hash, if it exists,
                followed by attributes in the form 'key=value'.  All fields are
                space-separated; fields with spaces in the values are quoted.

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

                # Sort so that we get consistent action attribute ordering.
                # We pay a performance penalty to do so, but it seems worth it.
                for k in sorted(self.attrs.keys()):
                        v = self.attrs[k]
                        if isinstance(v, list):
                            str += " " + " ".join([
                                "%s=%s" % (k, q(lmt))
                                for lmt in v
                            ])
                        elif " " in v:
                                str += " " + k + "=\"" + v + "\""
                        else:
                                str += " " + k + "=" + v

                return str

        def __cmp__(self, other):
                """Compare actions for ordering.  The ordinality of a
                   given action is computed and stored at action
                   initialization."""

                res = cmp(self.ord, other.ord)
                if res == 0:
                        return self.compare(other) # often subclassed

                return res

        def compare(self, other):
                return cmp(id(self), id(other))

        def different(self, other):
                """Returns True if other represents a non-ignorable change from self.

                By default, this means two actions are different if any of their
                attributes are different.  Subclasses should override this
                behavior when appropriate.
                """

                # We could ignore key_attr, or possibly assert that it's the
                # same.
                sset = set(self.attrs.keys())
                oset = set(other.attrs.keys())
                if sset.symmetric_difference(oset):
                        return True

                for a in self.attrs:
                        if self.attrs[a] != other.attrs[a]:
                                return True

                if hasattr(self, "hash"):
                        assert(hasattr(other, "hash"))
                        if self.hash != other.hash:
                                return True

                return False

        def differences(self, other):
                """Returns a list of attributes that have different values
                between other and self"""
                sset = set(self.attrs.keys())
                oset = set(other.attrs.keys())
                l = list(sset.symmetric_difference(oset))
                l.extend([ k
                           for k in sset.intersection(oset)
                           if self.attrs[k] != other.attrs[k]
                           ])
                return (l)

        def generate_indices(self):
                """Generate for the reverse index database data for this action.

                See pkg.client.pkgplan.make_indices for more information about
                the reverse index database.

                This method returns a dictionary mapping attribute names to
                their values.  This is not simply the action attribute
                dictionary, 'attrs', as not necessarily all of these attributes
                are interesting to look up, and there may be others which are
                derived from the canonical attributes (like the path's basename).
                """

                indices = {}

                # XXX What about derived indices -- those which aren't one of
                # the attributes, such as basename?  Just push computing them
                # into the subclasses?  Or is this simple enough that we have no
                # need for a generic.generate_indices() that does anything
                # interesting?
                if hasattr(self, "reverse_indices"):
                        indices.update(
                            (idx, self.attrs[idx])
                            for idx in self.reverse_indices
                        )

                if hasattr(self, "hash"):
                        indices["content"] = self.hash

                return indices

        def distinguished_name(self):
                """ Return the distinguishing name for this action,
                    preceded by the type of the distinguishing name.  For
                    example, for a file action, 'path' might be the
                    key_attr.  So, the distinguished name might be
                    "path: usr/lib/libc.so.1".
                """

                if self.key_attr == None:
                        return str(self)
                return "%s: %s" % \
                    (self.name, self.attrs.get(self.key_attr, "???"))

        @staticmethod
        def makedirs(path, **kw):
                """Make directory specified by 'path' with given permissions, as
                well as all missing parent directories.  Permissions are
                specified by the keyword arguments 'mode', 'uid', and 'gid'.

                The difference between this and os.makedirs() is that the
                permissions specify only those of the leaf directory.  Missing
                parent directories inherit the permissions of the deepest
                existing directory.  The leaf directory will also inherit any
                permissions not explicitly set."""

                # generate the components of the path.  The first
                # element will be empty since all absolute paths
                # always start with a root specifier.
                pathlist = portable.split_path(path)

                # Fill in the first path with the root of the filesystem
                # (this ends up being something like C:\ on windows systems,
                # and "/" on unix.
                pathlist[0] = portable.get_root(path)

                g = enumerate(pathlist)
                for i, e in g:
                        if not os.path.isdir(os.path.join(*pathlist[:i + 1])):
                                break
                else:
                        # XXX Because the filelist codepath may create directories with
                        # incorrect permissions (see pkgtarfile.py), we need to correct
                        # those permissions here.  Note that this solution relies on all
                        # intermediate directories being explicitly created by the
                        # packaging system; otherwise intermediate directories will  not
                        # get their permissions corrected.

                        stat = os.stat(path)
                        mode = kw.get("mode", stat.st_mode)
                        uid = kw.get("uid", stat.st_uid)
                        gid = kw.get("gid", stat.st_gid)
                        try:
                                if mode != stat.st_mode:
                                        os.chmod(path, mode)
                                if uid != stat.st_uid or gid != stat.st_gid:
                                        portable.chown(path, uid, gid)
                        except  OSError, e:
                                if e.errno != errno.EPERM and \
                                    e.errno != errno.ENOSYS:
                                        raise
                        return

                stat = os.stat(os.path.join(*pathlist[:i]))
                for i, e in g:
                        p = os.path.join(*pathlist[:i])
                        os.mkdir(p, stat.st_mode)
                        os.chmod(p, stat.st_mode)
                        try:
                                portable.chown(p, stat.st_uid, stat.st_gid)
                        except OSError, e:
                                if e.errno != errno.EPERM:
                                        raise

                # Create the leaf with any requested permissions, substituting
                # missing perms with the parent's perms.
                mode = kw.get("mode", stat.st_mode)
                uid = kw.get("uid", stat.st_uid)
                gid = kw.get("gid", stat.st_gid)
                os.mkdir(path, mode)
                os.chmod(path, mode)
                try:
                        portable.chown(path, uid, gid)
                except OSError, e:
                        if e.errno != errno.EPERM:
                                raise

        def verify(self, img, **args):
                """returns True if correctly installed in the given image"""
                return ["verify method for action type %s unimplemented" % self.name]

        def needsdata(self, orig):
                """Returns True if the action transition requires a
                datastream."""
                return False

        def attrlist(self, name):
                """return list containing value of named attribute."""
                value = self.attrs.get(name, [])
                if isinstance(value, list):
                        return value
                else:
                        return [ value ]

        def directory_references(self):
                """ returns references to paths in action"""
                if "path" in self.attrs:
                        return [os.path.dirname(os.path.normpath(self.attrs["path"]))]
                return []

        def preinstall(self, pkgplan, orig):
                """Client-side method that performs pre-install actions."""
                pass

        def install(self, pkgplan, orig):
                """Client-side method that installs the object."""
                pass

        def postinstall(self, pkgplan, orig):
                """Client-side method that performs post-install actions."""
                pass

        def preremove(self, pkgplan):
                """Client-side method that performs pre-remove actions."""
                pass

        def remove(self, pkgplan):
                """Client-side method that removes the object."""
                pass

        def postremove(self, pkgplan):
                """Client-side method that performs post-remove actions."""
                pass
