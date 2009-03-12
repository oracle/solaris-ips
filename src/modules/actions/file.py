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

#
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

"""module describing a file packaging object

This module contains the FileAction class, which represents a file-type
packaging object."""

import os
import errno
import tempfile
import stat
import generic
import pkg.misc as misc
import pkg.portable as portable
import pkg.client.api_errors as api_errors
import pkg.actions
try:
        import pkg.elf as elf
        haveelf = True
except ImportError:
        haveelf = False

class FileAction(generic.Action):
        """Class representing a file-type packaging object."""

        name = "file"
        attributes = ("mode", "owner", "group", "path")
        key_attr = "path"

        def __init__(self, data=None, **attrs):
                generic.Action.__init__(self, data, **attrs)
                self.hash = "NOHASH"
                self.replace_required = False
                if "path" in self.attrs:
                        self.attrs["path"] = self.attrs["path"].lstrip(
                            os.path.sep)
                        if not self.attrs["path"]:
                                raise pkg.actions.InvalidActionError(
                                    str(self), _("Empty path attribute"))

        # this check is only needed on Windows
        if portable.ostype == "windows":
                def preinstall(self, pkgplan, orig):
                        """If the file exists, check if it is in use."""
                        if not orig:
                                return
                        path = os.path.normpath(
                            os.path.join(pkgplan.image.get_root(),
                            orig.attrs["path"]))
                        if os.path.isfile(path) and self.in_use(path):
                                raise api_errors.FileInUseException, path

                def preremove(self, pkgplan):
                        path = os.path.normpath(
                            os.path.join(pkgplan.image.get_root(),
                            self.attrs["path"]))
                        if os.path.isfile(path) and self.in_use(path):
                                raise api_errors.FileInUseException, path

                def in_use(self, path):
                        """Determine if a file is in use (locked) by trying
                        to rename the file to itself."""
                        try:
                                os.rename(path, path)
                        except OSError, err:
                                if err.errno != errno.EACCES:
                                        raise
                                return True
                        return False

        def install(self, pkgplan, orig):
                """Client-side method that installs a file."""
                path = self.attrs["path"]
                mode = int(self.attrs["mode"], 8)
                owner = pkgplan.image.get_user_by_name(self.attrs["owner"])
                group = pkgplan.image.get_group_by_name(self.attrs["group"])

                final_path = os.path.normpath(os.path.sep.join(
                    (pkgplan.image.get_root(), path)))

                if not os.path.exists(os.path.dirname(final_path)):
                        self.makedirs(os.path.dirname(final_path), mode=0755)

                # XXX If we're upgrading, do we need to preserve file perms from
                # exisiting file?

                # check if we have a save_file active; if so, simulate file
                # being already present rather than installed from scratch

                if "save_file" in self.attrs:
                        orig = self.restore_file(pkgplan.image)

                # If the action has been marked with a preserve attribute, and
                # the file exists and has a contents hash different from what
                # the system expected it to be, then we preserve the original
                # file in some way, depending on the value of preserve.
                #
                # XXX What happens when we transition from preserve to
                # non-preserve or vice versa? Do we want to treat a preserve
                # attribute as turning the action into a critical action?
                if "preserve" in self.attrs and os.path.isfile(final_path):
                        chash, cdata = misc.get_data_digest(final_path)

                        # XXX We should save the originally installed file.  It
                        # can be used as an ancestor for a three-way merge, for
                        # example.  Where should it be stored?
                        if not orig or chash != orig.hash:
                                pres_type = self.attrs["preserve"]
                                if pres_type == "renameold":
                                        old_path = final_path + ".old"
                                elif pres_type == "renamenew":
                                        final_path = final_path + ".new"
                                else:
                                        return

                # If it is a directory (and not empty) then we should
                # salvage the contents.
                if os.path.exists(final_path) and \
                    not os.path.islink(final_path) and \
                    os.path.isdir(final_path):
                        try:    
                                os.rmdir(final_path)
                        except OSError, e:
                                if e.errno == errno.ENOENT:
                                        pass
                                elif e.errno == errno.EEXIST or \
                                            e.errno == errno.ENOTEMPTY:
                                        pkgplan.image.salvagedir(final_path)
                                elif e.errno != errno.EACCES:
                                        # this happens on Windows
                                        raise

                # XXX This needs to be modularized.
                # XXX This needs to be controlled by policy.
                if self.needsdata(orig):
                        tfilefd, temp = tempfile.mkstemp(dir=os.path.dirname(
                            final_path))
                        stream = self.data()
                        tfile = os.fdopen(tfilefd, "wb")
                        shasum = misc.gunzip_from_stream(stream, tfile)

                        tfile.close()
                        stream.close()

                        # XXX Should throw an exception if shasum doesn't match
                        # self.hash
                else:
                        temp = final_path

                try:
                        os.chmod(temp, mode)
                except OSError, e:
                        # If the file didn't exist, assume that's intentional,
                        # and drive on.
                        if e.errno != errno.ENOENT:
                                raise
                        else:
                                return

                try:
                        portable.chown(temp, owner, group)
                except OSError, e:
                        if e.errno != errno.EPERM:
                                raise

                # XXX There's a window where final_path doesn't exist, but we
                # probably don't care.
                if "old_path" in locals():
                        portable.rename(final_path, old_path)

                # This is safe even if temp == final_path.
                portable.rename(temp, final_path)

                # Handle timestamp if specified
                if "timestamp" in self.attrs:
                        t = misc.timestamp_to_time(self.attrs["timestamp"])
                        os.utime(final_path, (t, t))

        def verify(self, img, **args):
                """ verify that file is present and if preserve attribute
                not present, that hashes match"""
                path = self.attrs["path"]
                mode = int(self.attrs["mode"], 8)
                owner = img.get_user_by_name(self.attrs["owner"])
                group = img.get_group_by_name(self.attrs["group"])

                path = os.path.normpath(os.path.sep.join(
                    (img.get_root(), path)))

                errors = []

                try:
                        fs = os.lstat(path)
                except OSError, e:
                        if e.errno == errno.ENOENT:
                                self.replace_required = True
                                errors.append("File does not exist")
                        elif e.errno == errno.EACCES:
                                errors.append("Skipping: Permission denied")
                        else:
                                errors.append("Unexpected OSError: %s" % e)

                # If we have errors already there isn't much point in
                # continuing.
                if errors:
                        return errors

                if path.lower().endswith("/cat") and args["verbose"] == True:
                        errors.append("Warning: package may contain bobcat!  "
                            "(http://xkcd.com/325/)")

                if not stat.S_ISREG(fs.st_mode):
                        errors.append("%s is not a regular file" % \
                            self.attrs["path"])
                        self.replace_required = True

                if fs.st_uid != owner:
                        errors.append("Owner: '%s' should be '%s'" % \
                            (img.get_name_by_uid(fs.st_uid, True),
                             img.get_name_by_uid(owner, True)))
                if fs.st_gid != group:
                        errors.append("Group: '%s' should be '%s'" % \
                            (img.get_name_by_gid(fs.st_gid, True),
                             img.get_name_by_gid(group, True)))
                if stat.S_IMODE(fs.st_mode) != mode:
                        errors.append("Mode: 0%.3o should be 0%.3o" % \
                            (stat.S_IMODE(fs.st_mode), mode))

                if "timestamp" in self.attrs and fs.st_mtime != \
                    misc.timestamp_to_time(self.attrs["timestamp"]):
                        errors.append("Timestamp: %s should be %s" %
                            (misc.time_to_timestamp(fs.st_mtime), 
                            self.attrs["timestamp"]))
                             
                # avoid checking pkg.size if elfhash present;
                # different size files may have the same elfhash
                if "preserve" not in self.attrs and \
                    "pkg.size" in self.attrs and    \
                    "elfhash" not in self.attrs and \
                    fs.st_size != int(self.attrs["pkg.size"]):
                        errors.append("Size: %d bytes should be %d" % \
                            (fs.st_size, int(self.attrs["pkg.size"])))

                if "preserve" in self.attrs:
                        return errors

                if args["forever"] != True:
                        return errors

                #
                # Check file contents
                #
                try:
                        elfhash = None
                        elferror = None
                        if "elfhash" in self.attrs and haveelf:
                                #
                                # It's possible for the elf module to
                                # throw while computing the hash,
                                # especially if the file is badly
                                # corrupted or truncated.
                                #
                                try:
                                        elfhash = elf.get_dynamic(path)["hash"]
                                except RuntimeError, e:
                                        errors.append("Elfhash: %s" % e)

                                if elfhash is not None and elfhash != self.attrs["elfhash"]:
                                        elferror = "Elfhash: %s should be %s" % \
                                            (elfhash, self.attrs["elfhash"])

                        # If we failed to compute the content hash, or the
                        # content hash failed to verify, try the file hash.
                        # If the content hash fails to match but the file hash
                        # matches, it indicates that the content hash algorithm
                        # changed, since obviously the file hash is a superset
                        # of the content hash.
                        if elfhash is None or elferror:
                                hashvalue, data = misc.get_data_digest(path)
                                if hashvalue != self.hash:
                                        # Prefer the content hash error message.
                                        if elferror:
                                                errors.append(elferror)
                                        else:
                                                errors.append("Hash: %s should be %s" % \
                                                    (hashvalue, self.hash))
                                        self.replace_required = True
                except EnvironmentError, e:
                        if e.errno == errno.EACCES:
                                errors.append("Skipping: Permission Denied" % e)
                        else:
                                errors.append("Unexpected Error %s" % e)
                except KeyboardInterrupt:
                        # This is not really unexpected...
                        raise
                except Exception, e:
                        errors.append("Unexpected Exception: %s" % e)

                return errors

        # If we're not upgrading, or the file contents have changed,
        # retrieve the file and write it to a temporary location.
        # For ELF files, only write the new file if the elfhash changed.
        def needsdata(self, orig):
                if self.replace_required:
                        return True
                bothelf = orig and "elfhash" in orig.attrs and \
                    "elfhash" in self.attrs
                if not orig or \
                    (orig.hash != self.hash and (not bothelf or
                        orig.attrs["elfhash"] != self.attrs["elfhash"])):
                        return True

                return False
                

        def remove(self, pkgplan):
                path = os.path.normpath(os.path.sep.join(
                    (pkgplan.image.get_root(), self.attrs["path"])))

                # are we supposed to save this file to restore it elsewhere
                # or in another pkg?
                if "save_file" in self.attrs:
                        self.save_file(pkgplan.image, path)

                try:
                        # Make file writable so it can be deleted
                        os.chmod(path, stat.S_IWRITE|stat.S_IREAD)
                        portable.remove(path)
                except OSError,e:
                        if e.errno != errno.ENOENT:
                                raise


        def different(self, other):
                # Override the generic different() method to ignore the file
                # hash for ELF files and compare the ELF hash instead.
                # XXX This should be modularized and controlled by policy.

                # One of these isn't an ELF file, so call the generic method
                if "elfhash" not in self.attrs or "elfhash" not in other.attrs:
                        return generic.Action.different(self, other)

                sset = set(self.attrs.keys())
                oset = set(other.attrs.keys())
                if sset.symmetric_difference(oset):
                        return True

                for a in self.attrs:
                        if self.attrs[a] != other.attrs[a]:
                                return True

                return False

        def generate_indices(self):
                return [
                    ("file", "content", self.hash, self.hash),
                    ("file", "basename", os.path.basename(self.attrs["path"]),
                    None),
                    ("file", "path", os.path.sep + self.attrs["path"], None)
                ]

        def save_file(self, image, full_path):
                """save a file for later (in same process invocation) 
                installation"""

                saved_name = image.temporary_file()
                misc.copyfile(full_path, saved_name)
                 
                image.saved_files[self.attrs["save_file"]] = (self, saved_name)

        def restore_file(self, image):
                """restore a previously saved file; return cached action """


                path = self.attrs["path"]

                orig, saved_name = image.saved_files[self.attrs["save_file"]]
                full_path = os.path.normpath(os.path.sep.join(
                    (image.get_root(), path)))

                assert(not os.path.exists(full_path))

                misc.copyfile(saved_name, full_path)
                os.unlink(saved_name)

                return orig
