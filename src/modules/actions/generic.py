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

"""module describing a generic packaging object

This module contains the Action class, which represents a generic packaging
object."""

from cStringIO import StringIO
import errno
import os
try:
        # Some versions of python don't have these constants.
        os.SEEK_SET
except AttributeError:
        os.SEEK_SET, os.SEEK_CUR, os.SEEK_END = range(3)
import pkg.actions
import pkg.portable as portable
import pkg.variant as variant
import stat

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
                        "legacy",
                        "signature"
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

                Any remaining named arguments will be treated as attributes.
                """

                if not self.orderdict:
                        self.loadorderdict()
                self.ord = self.orderdict.get(type(self), self.unknown)

                self.attrs = attrs

                # Since this is a hot path, avoid a function call unless
                # absolutely necessary.
                if data is None:
                        self.data = None
                else:
                        self.set_data(data)

        def set_data(self, data):
                """This function sets the data field of the action.

                The "data" parameter is the file to use to set the data field.
                It can be a string which is the path to the file, a function
                which provides the file when called, or a file handle to the
                file."""

                if data is None:
                        self.data = None
                        return

                if isinstance(data, basestring):
                        if not os.path.exists(data):
                                raise pkg.actions.ActionDataError(
                                    _("No such file: '%s'.") % data, path=data)
                        elif os.path.isdir(data):
                                raise pkg.actions.ActionDataError(
                                    _("'%s' is not a file.") % data, path=data)

                        def file_opener():
                                return open(data, "rb")
                        self.data = file_opener
                        if "pkg.size" not in self.attrs:
                                try:
                                        fs = os.stat(data)
                                        self.attrs["pkg.size"] = str(fs.st_size)
                                except EnvironmentError, e:
                                        raise \
                                            pkg.actions.ActionDataError(
                                            e, path=data)
                        return

                if callable(data):
                        # Data is not None, and is callable.
                        self.data = data
                        return

                if "pkg.size" in self.attrs:
                        self.data = lambda: data
                        return

                try:
                        sz = data.size
                except AttributeError:
                        try:
                                try:
                                        sz = os.fstat(data.fileno()).st_size
                                except (AttributeError, TypeError):
                                        try:
                                                try:
                                                        data.seek(0,
                                                            os.SEEK_END)
                                                        sz = data.tell()
                                                        data.seek(0)
                                                except (AttributeError,
                                                    TypeError):
                                                        d = data.read()
                                                        sz = len(d)
                                                        data = StringIO(d)
                                        except (AttributeError, TypeError):
                                                # Raw data was provided; fake a
                                                # file object.
                                                sz = len(data)
                                                data = StringIO(data)
                        except EnvironmentError, e:
                                raise pkg.actions.ActionDataError(e)

                self.attrs["pkg.size"] = str(sz)
                self.data = lambda: data

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

                out = self.name
                if hasattr(self, "hash"):
                        out += " " + self.hash

                def q(s):
                        if " " in s or s == "":
                                return '"%s"' % s
                        else:
                                return s

                # Sort so that we get consistent action attribute ordering.
                # We pay a performance penalty to do so, but it seems worth it.
                for k in sorted(self.attrs.keys()):
                        v = self.attrs[k]
                        if isinstance(v, list) or isinstance(v, set):
                                out += " " + " ".join([
                                    "%s=%s" % (k, q(lmt)) for lmt in v
                                ])
                        elif " " in v or v == "":
                                out += " " + k + "=\"" + v + "\""
                        else:
                                out += " " + k + "=" + v

                return out

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
                """Returns True if other represents a non-ignorable change from
                self.

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
                """Generate the information needed to index this action.

                This method, and the overriding methods in subclasses, produce
                a list of four-tuples.  The tuples are of the form
                (action_name, key, token, full value).  action_name is the
                string representation of the kind of action generating the
                tuple.  'file' and 'depend' are two examples.  It is required to
                not be None.  Key is the string representation of the name of
                the attribute being indexed.  Examples include 'basename' and
                'path'.  Token is the token to be searched against.  Full value
                is the value to display to the user in the event this token
                matches their query.  This is useful for things like categories
                where what matched the query may be a substring of what the
                desired user output is.
                """

                if hasattr(self, "hash"):
                        return [
                            (self.name, "content", self.hash, self.hash),
                        ]
                return []

        def distinguished_name(self):
                """ Return the distinguishing name for this action,
                    preceded by the type of the distinguishing name.  For
                    example, for a file action, 'path' might be the
                    key_attr.  So, the distinguished name might be
                    "path: usr/lib/libc.so.1".
                """

                if self.key_attr is None:
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
                        # XXX Because the filelist codepath may create
                        # directories with incorrect permissions (see
                        # pkgtarfile.py), we need to correct those permissions
                        # here.  Note that this solution relies on all
                        # intermediate directories being explicitly created by
                        # the packaging system; otherwise intermediate
                        # directories will not get their permissions corrected.
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

        def get_varcet_keys(self):
                """Return the names of any facet or variant tags in this
                action."""

                variants = []
                facets = []

                for k in self.attrs.iterkeys():
                        if k.startswith("variant."):
                                variants.append(k)
                        if k.startswith("facet."):
                                facets.append(k)
                return variants, facets

        def get_variants(self):
                return variant.VariantSets(dict((
                    (v, self.attrs[v]) for v in self.get_varcet_keys()[0]
                )))

        def verify(self, img, **args):
                """Returns an empty list if correctly installed in the given
                image."""
                return []

        def verify_fsobj_common(self, img, ftype):

                errors = []
                abort = False
                def ftype_to_name(ftype):
                        assert ftype is not None
                        tmap = {
                                stat.S_IFIFO: "fifo",
                                stat.S_IFCHR: "character device",
                                stat.S_IFDIR: "directory",
                                stat.S_IFBLK: "block device",
                                stat.S_IFREG: "regular file",
                                stat.S_IFLNK: "symbolic link",
                                stat.S_IFSOCK: "socket",
                        }
                        if ftype in tmap:
                                return tmap[ftype]
                        else:
                                return "Unknown (0x%x)" % ftype

                mode = owner = group = None
                if "mode" in self.attrs:
                        mode = int(self.attrs["mode"], 8)
                if "owner" in self.attrs:
                        owner = img.get_user_by_name(self.attrs["owner"])
                if "group" in self.attrs:
                        group = img.get_group_by_name(self.attrs["group"])

                path = os.path.normpath(
                    os.path.sep.join((img.get_root(), self.attrs["path"])))

                lstat = None
                try:
                        lstat = os.lstat(path)
                except OSError, e:
                        if e.errno == errno.ENOENT:
                                errors.append("Missing: %s does not exist" %
                                    ftype_to_name(ftype))
                        elif e.errno == errno.EACCES:
                                errors.append("Skipping: Permission denied")
                        else:
                                errors.append("Unexpected OSError: %s" % e)
                        abort = True

                if abort:
                        return lstat, errors, abort

                if ftype is not None and ftype != stat.S_IFMT(lstat.st_mode):
                        errors.append("File Type: '%s' should be '%s'" %
                            (ftype_to_name(stat.S_IFMT(lstat.st_mode)),
                             ftype_to_name(ftype)))
                        abort = True

                if owner is not None and lstat.st_uid != owner:
                        errors.append("Owner: '%s (%d)' should be '%s (%d)'" %
                            (img.get_name_by_uid(lstat.st_uid, True),
                            lstat.st_uid, self.attrs["owner"], owner))

                if group is not None and lstat.st_gid != group:
                        errors.append("Group: '%s (%s)' should be '%s (%s)'" %
                            (img.get_name_by_gid(lstat.st_gid, True),
                            lstat.st_gid, self.attrs["group"], group))

                if mode is not None and stat.S_IMODE(lstat.st_mode) != mode:
                        errors.append("Mode: 0%.3o should be 0%.3o" %
                            (stat.S_IMODE(lstat.st_mode), mode))
                return lstat, errors, abort

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
                """Returns references to paths in action."""
                if "path" in self.attrs:
                        return [os.path.dirname(os.path.normpath(
                            self.attrs["path"]))]
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

        def include_this(self, excludes):
                """Callables in excludes list returns True
                if action is to be included, False if
                not"""
                for c in excludes:
                        if not c(self):
                                return False
                return True
