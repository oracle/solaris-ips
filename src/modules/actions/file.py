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
# Copyright (c) 2007, 2011, Oracle and/or its affiliates. All rights reserved.
#

"""module describing a file packaging object

This module contains the FileAction class, which represents a file-type
packaging object."""

import os
import errno
import tempfile
import stat
import generic
import zlib

import pkg.actions
import pkg.client.api_errors as api_errors
import pkg.misc as misc
import pkg.portable as portable

from pkg.client.api_errors import ActionExecutionError

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
        unique_attrs = "path", "mode", "owner", "group", "preserve"
        globally_identical = True
        namespace_group = "path"

        has_payload = True

        def __init__(self, data=None, **attrs):
                generic.Action.__init__(self, data, **attrs)
                self.hash = "NOHASH"
                self.replace_required = False

        def __getstate__(self):
                """This object doesn't have a default __dict__, instead it
                stores its contents via __slots__.  Hence, this routine must
                be provide to translate this object's contents into a
                dictionary for pickling"""

                pstate = generic.Action.__getstate__(self)
                state = {}
                for name in FileAction.__slots__:
                        if not hasattr(self, name):
                                continue
                        state[name] = getattr(self, name)
                return (state, pstate)

        def __setstate__(self, state):
                """This object doesn't have a default __dict__, instead it
                stores its contents via __slots__.  Hence, this routine must
                be provide to translate a pickled dictionary copy of this
                object's contents into a real in-memory object."""

                (state, pstate) = state
                generic.Action.__setstate__(self, pstate)
                for name in state:
                        setattr(self, name, state[name])

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
                elif not orig and not pkgplan.origin_fmri and \
                     "preserve" in self.attrs and os.path.isfile(final_path):
                        # Unpackaged editable file is already present during
                        # initial install; salvage it before continuing.
                        pkgplan.salvage(final_path)

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
                old_path = None
                if pres_type == True or (pres_type and
                    pkgplan.origin_fmri == pkgplan.destination_fmri):
                        # File is marked to be preserved and exists so don't
                        # reinstall content.
                        do_content = False
                elif pres_type == "legacy":
                        # Only rename old file if this is a transition to
                        # preserve=legacy from something else.
                        if orig.attrs.get("preserve", None) != "legacy":
                                old_path = final_path + ".legacy"
                elif pres_type == "renameold.update":
                        old_path = final_path + ".update"
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
                                        pkgplan.salvage(final_path)
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
                        try:
                                shasum = misc.gunzip_from_stream(stream, tfile)
                        except zlib.error, e:
                                raise ActionExecutionError(self,
                                    details=_("Error decompressing payload: %s")
                                    % (" ".join([str(a) for a in e.args])),
                                    error=e)
                        finally:
                                tfile.close()
                                stream.close()

                        if shasum != self.hash:
                                raise ActionExecutionError(self,
                                    details=_("Action data hash verification "
                                    "failure: expected: %(expected)s computed: "
                                    "%(actual)s action: %(action)s") % {
                                        "expected": self.hash,
                                        "actual": shasum,
                                        "action": self
                                    })
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
                if do_content and old_path:
                        try:
                                portable.rename(final_path, old_path)
                        except OSError, e:
                                if e.errno != errno.ENOENT:
                                        # Only care if file isn't gone already.
                                        raise

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
                        self.replace_required = True
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
                        # This is a generic mechanism, but only used for libc on
                        # x86, where the "best" version of libc is lofs-mounted
                        # on the canonical path, foiling the standard verify
                        # checks.
                        is_mtpt = self.attrs.get("mountpoint", "").lower() == "true"
                        elfhash = None
                        elferror = None
                        if "elfhash" in self.attrs and haveelf and not is_mtpt:
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
                        if (elfhash is None or elferror) and not is_mtpt:
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
                the strings 'renameold', 'renameold.update', 'renamenew',
                or 'legacy' for each of the respective forms of preservation.
                """

                try:
                        pres_type = self.attrs["preserve"]
                except KeyError:
                        return None

                final_path = os.path.normpath(os.path.sep.join(
                    (pkgplan.image.get_root(), self.attrs["path"])))

                # 'legacy' preservation is very different than other forms of
                # preservation as it doesn't account for the on-disk state of
                # the action's payload.
                if pres_type == "legacy":
                        if not orig:
                                # This is an initial install or a repair, so
                                # there's nothing to deliver.
                                return True
                        return pres_type

                # If action has been marked with a preserve attribute, the
                # hash of the preserved file has changed between versions,
                # and the package being installed is older than the package
                # that was installed, and the version on disk is different
                # than the installed package's original version, then preserve
                # the installed file by renaming it.
                #
                # If pkgplan.origin_fmri isn't set, but there is an orig action,
                # then this file is moving between packages and it can't be
                # a downgrade since that isn't allowed across rename or obsolete
                # boundaries.
                is_file = os.path.isfile(final_path)
                if orig and pkgplan.destination_fmri and \
                    self.hash != orig.hash and \
                    pkgplan.origin_fmri and \
                    pkgplan.destination_fmri.version < pkgplan.origin_fmri.version:
                        # Installed, preserved file is for a package newer than
                        # what will be installed.  So check if the version on
                        # disk is different than what was originally delivered,
                        # and if so, preserve it.
                        if is_file:
                                ihash, cdata = misc.get_data_digest(final_path)
                                if ihash != orig.hash:
                                        # .old is intentionally avoided here to
                                        # prevent accidental collisions with the
                                        # normal install process.
                                        return "renameold.update"
                        return False

                # If the action has been marked with a preserve attribute, and
                # the file exists and has a content hash different from what the
                # system expected it to be, then we preserve the original file
                # in some way, depending on the value of preserve.  If the
                # action is an overlay, then we always overwrite.
                overlay = self.attrs.get("overlay") == "true"
                if is_file and not overlay:
                        chash, cdata = misc.get_data_digest(final_path)
                        if not orig or chash != orig.hash:
                                if pres_type in ("renameold", "renamenew"):
                                        return pres_type
                                return True

                return False

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

                pres_type = self.__check_preserve(orig, pkgplan)
                if pres_type != None and pres_type != True:
                        # Preserved files only need data if they're being
                        # changed (e.g. "renameold", etc.).
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

                if not pkgplan.destination_fmri and \
                    self.attrs.get("preserve", "false").lower() != "false":
                        # Preserved files are salvaged if they have been
                        # modified since they were installed and this is
                        # not an upgrade.
                        try:
                                ihash, cdata = misc.get_data_digest(path)
                                if ihash != self.hash:
                                        pkgplan.salvage(path)
                                        # Nothing more to do.
                                        return
                        except EnvironmentError, e:
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

                errors = generic.Action._validate(self, fmri=fmri,
                    numeric_attrs=("pkg.csize", "pkg.size"), raise_errors=False,
                    required_attrs=("owner", "group"), single_attrs=("chash",
                    "preserve", "overlay", "elfarch", "elfbits", "elfhash",
                    "original_name"))
                errors.extend(self._validate_fsobj_common())
                if errors:
                        raise pkg.actions.InvalidActionAttributesError(self,
                            errors, fmri=fmri)
