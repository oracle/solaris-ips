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
# Copyright 2010 Sun Microsystems, Inc.  All rights reserved.
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

        __slots__ = ["hash", "replace_required"]

        name = "file"
        key_attr = "path"
        globally_unique = True

        def __init__(self, data=None, **attrs):
                generic.Action.__init__(self, data, **attrs)
                self.hash = "NOHASH"
                self.replace_required = False
                if "path" in self.attrs:
                        self.attrs["path"] = self.attrs["path"].lstrip("/")
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

                mode = None
                try:
                        mode = int(self.attrs.get("mode", None), 8)
                except (TypeError, ValueError):
                        # Mode isn't valid, so let validate raise a more
                        # informative error.
                        self.validate(fmri=pkgplan.destination_fmri)

                owner, group = self.get_fsobj_uid_gid(pkgplan,
                    pkgplan.destination_fmri)

                final_path = os.path.normpath(os.path.sep.join(
                    (pkgplan.image.get_root(), self.attrs["path"])))

                # Don't allow installation through symlinks.
                self.fsobj_checkpath(pkgplan, final_path)

                if not os.path.exists(os.path.dirname(final_path)):
                        self.makedirs(os.path.dirname(final_path),
                            mode=misc.PKG_DIR_MODE,
                            fmri=pkgplan.destination_fmri)

                # XXX If we're upgrading, do we need to preserve file perms from
                # existing file?

                # check if we have a save_file active; if so, simulate file
                # being already present rather than installed from scratch

                if "save_file" in self.attrs:
                        orig = self.restore_file(pkgplan.image)

                # See if we need to preserve the file, and if so, set that up.
                #
                # XXX What happens when we transition from preserve to
                # non-preserve or vice versa? Do we want to treat a preserve
                # attribute as turning the action into a critical action?
                #
                # XXX We should save the originally installed file.  It can be
                # used as an ancestor for a three-way merge, for example.  Where
                # should it be stored?
                pres_type = self.__check_preserve(orig, pkgplan)
                do_content = True
                if pres_type == True or (pres_type and
                    pkgplan.origin_fmri == pkgplan.destination_fmri):
                        # File is marked to be preserved and exists so don't
                        # reinstall content.
                        do_content = False
                elif pres_type == "renameold":
                        old_path = final_path + ".old"
                elif pres_type == "renamenew":
                        final_path = final_path + ".new"

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
                                elif e.errno in (errno.EEXIST, errno.ENOTEMPTY):
                                        pkgplan.image.salvage(final_path)
                                elif e.errno != errno.EACCES:
                                        # this happens on Windows
                                        raise

                # XXX This needs to be modularized.
                # XXX This needs to be controlled by policy.
                if do_content and self.needsdata(orig, pkgplan):
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
                if do_content and pres_type == "renameold":
                        portable.rename(final_path, old_path)

                # This is safe even if temp == final_path.
                portable.rename(temp, final_path)

                # Handle timestamp if specified (and content was installed).
                if do_content and "timestamp" in self.attrs:
                        t = misc.timestamp_to_time(self.attrs["timestamp"])
                        try:
                                os.utime(final_path, (t, t))
                        except OSError, e:
                                if e.errno != errno.EACCES:
                                        raise

                                # On Windows, the time cannot be changed on a
                                # read-only file
                                os.chmod(final_path, stat.S_IRUSR|stat.S_IWUSR)
                                os.utime(final_path, (t, t))
                                os.chmod(final_path, mode)

        def verify(self, img, **args):
                """Returns a tuple of lists of the form (errors, warnings,
                info).  The error list will be empty if the action has been
                correctly installed in the given image.

                In detail, this verifies that the file is present, and if
                the preserve attribute is not present, that the hashes
                and other attributes of the file match."""

                path = os.path.normpath(os.path.sep.join(
                    (img.get_root(), self.attrs["path"])))

                lstat, errors, warnings, info, abort = \
                    self.verify_fsobj_common(img, stat.S_IFREG)
                if lstat:
                        if not stat.S_ISREG(lstat.st_mode):
                                self.replace_required = True

                if abort:
                        assert errors
                        return errors, warnings, info

                if path.lower().endswith("/bobcat") and args["verbose"] == True:
                        # Returned as a purely informational (untranslated)
                        # message so that no client should interpret it as a
                        # reason to fail verification.
                        info.append("Warning: package may contain bobcat!  "
                            "(http://xkcd.com/325/)")

                if "preserve" not in self.attrs and \
                    "timestamp" in self.attrs and lstat.st_mtime != \
                    misc.timestamp_to_time(self.attrs["timestamp"]):
                        errors.append(_("Timestamp: %(found)s should be "
                            "%(expected)s") % {
                            "found": misc.time_to_timestamp(lstat.st_mtime),
                            "expected": self.attrs["timestamp"] })

                # avoid checking pkg.size if elfhash present;
                # different size files may have the same elfhash
                if "preserve" not in self.attrs and \
                    "pkg.size" in self.attrs and    \
                    "elfhash" not in self.attrs and \
                    lstat.st_size != int(self.attrs["pkg.size"]):
                        errors.append(_("Size: %(found)d bytes should be "
                            "%(expected)d") % { "found": lstat.st_size,
                            "expected": int(self.attrs["pkg.size"]) })

                if "preserve" in self.attrs:
                        return errors, warnings, info

                if args["forever"] != True:
                        return errors, warnings, info

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

                                if elfhash is not None and \
                                    elfhash != self.attrs["elfhash"]:
                                        elferror = _("Elfhash: %(found)s "
                                            "should be %(expected)s") % {
                                            "found": elfhash,
                                            "expected": self.attrs["elfhash"] }

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
                                                errors.append(_("Hash: "
                                                    "%(found)s should be "
                                                    "%(expected)s") % {
                                                    "found": hashvalue,
                                                    "expected": self.hash })
                                        self.replace_required = True
                except EnvironmentError, e:
                        if e.errno == errno.EACCES:
                                errors.append(_("Skipping: Permission Denied"))
                        else:
                                errors.append(_("Unexpected Error: %s") % e)
                except Exception, e:
                        errors.append(_("Unexpected Exception: %s") % e)

                return errors, warnings, info

        def __check_preserve(self, orig, pkgplan):
                """Return the type of preservation needed for this action.

                Returns None if preservation is not defined by the action.
                Returns False if it is, but no preservation is necessary.
                Returns True for the normal preservation form.  Returns one of
                the strings 'renameold' or 'renamenew' for each of the
                respective forms of preservation.
                """

                if not "preserve" in self.attrs:
                        return None

                final_path = os.path.normpath(os.path.sep.join(
                    (pkgplan.image.get_root(), self.attrs["path"])))

                pres_type = False
                # If the action has been marked with a preserve attribute, and
                # the file exists and has a content hash different from what the
                # system expected it to be, then we preserve the original file
                # in some way, depending on the value of preserve.
                if os.path.isfile(final_path):
                        chash, cdata = misc.get_data_digest(final_path)

                        if not orig or chash != orig.hash:
                                pres_type = self.attrs["preserve"]
                                if pres_type in ("renameold", "renamenew"):
                                        return pres_type
                                else:
                                        return True
                return pres_type


        # If we're not upgrading, or the file contents have changed,
        # retrieve the file and write it to a temporary location.
        # For ELF files, only write the new file if the elfhash changed.
        def needsdata(self, orig, pkgplan):
                if self.replace_required:
                        return True
                bothelf = orig and "elfhash" in orig.attrs and \
                    "elfhash" in self.attrs
                if not orig or \
                    (orig.hash != self.hash and (not bothelf or
                        orig.attrs["elfhash"] != self.attrs["elfhash"])):
                        return True
                elif orig:
                        # It's possible that the file content hasn't changed
                        # for an upgrade case, but the file is missing.  This
                        # ensures that for cases where the mode or some other
                        # attribute of the file has changed that the file will
                        # be installed.
                        path = os.path.normpath(os.path.sep.join(
                            (pkgplan.image.get_root(), self.attrs["path"])))
                        if not os.path.isfile(path):
                                return True

                if self.__check_preserve(orig, pkgplan):
                        return True

                return False

        def remove(self, pkgplan):
                path = os.path.normpath(os.path.sep.join(
                    (pkgplan.image.get_root(), self.attrs["path"])))

                # Are we supposed to save this file to restore it elsewhere
                # or in another pkg?
                if "save_file" in self.attrs:
                        self.save_file(pkgplan.image, path)

                try:
                        # Make file writable so it can be deleted.
                        os.chmod(path, stat.S_IWRITE|stat.S_IREAD)
                except OSError, e:
                        if e.errno == errno.ENOENT:
                                # Already gone; don't care.
                                return
                        raise

                # Attempt to remove the file.
                self.remove_fsobj(pkgplan, path)

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
                """Generates the indices needed by the search dictionary.  See
                generic.py for a more detailed explanation."""

                return [
                    ("file", "content", self.hash, self.hash),
                    ("file", "basename", os.path.basename(self.attrs["path"]),
                    None),
                    ("file", "path", os.path.sep + self.attrs["path"], None)
                ]

        def save_file(self, image, full_path):
                """Save a file for later installation (in same process
                invocation, if it exists)."""

                saved_name = image.temporary_file()
                try:
                        misc.copyfile(full_path, saved_name)
                except OSError, err:
                        if err.errno != errno.ENOENT:
                                raise

                        # If the file doesn't exist, it can't be saved, so
                        # be certain consumers of this information know there
                        # isn't an original to restore.
                        saved_name = None

                ip = image.imageplan
                ip.saved_files[self.attrs["save_file"]] = (self, saved_name)

        def restore_file(self, image):
                """restore a previously saved file; return cached action """

                ip = image.imageplan
                orig, saved_name = ip.saved_files[self.attrs["save_file"]]
                if saved_name is None:
                        # Nothing to restore; original file is missing.
                        return

                path = self.attrs["path"]

                full_path = os.path.normpath(os.path.sep.join(
                    (image.get_root(), path)))

                assert(not os.path.exists(full_path))

                misc.copyfile(saved_name, full_path)
                os.unlink(saved_name)

                return orig

        def validate(self, fmri=None):
                """Performs additional validation of action attributes that
                for performance or other reasons cannot or should not be done
                during Action object creation.  An ActionError exception (or
                subclass of) will be raised if any attributes are not valid.
                This is primarily intended for use during publication or during
                error handling to provide additional diagonostics.

                'fmri' is an optional package FMRI (object or string) indicating
                what package contained this action."""

                return self.validate_fsobj_common(fmri=fmri)
