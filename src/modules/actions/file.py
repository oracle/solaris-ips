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
# Copyright (c) 2007, 2016, Oracle and/or its affiliates. All rights reserved.
#

"""module describing a file packaging object

This module contains the FileAction class, which represents a file-type
packaging object."""

import errno
from . import generic
import os
import six
import stat
import tempfile
import types
import zlib

from . import _common
import pkg.actions
import pkg.client.api_errors as api_errors
import pkg.digest as digest
import pkg.misc as misc
import pkg.portable as portable

from pkg.client.api_errors import ActionExecutionError
from pkg.client.debugvalues import DebugValues

try:
        import pkg.elf as elf
        haveelf = True
except ImportError:
        haveelf = False

# Once additional content-hashed file types are supported,
# have_content_hash can be derived from multiple sources.
have_content_hash = haveelf

class FileAction(generic.Action):
        """Class representing a file-type packaging object."""

        __slots__ = ["hash", "replace_required"]

        name = "file"
        key_attr = "path"
        unique_attrs = "path", "mode", "owner", "group", "preserve", "sysattr"
        globally_identical = True
        namespace_group = "path"
        ordinality = generic._orderdict[name]

        has_payload = True

        # __init__ is provided as a native function (see end of class
        # declaration).

        # this check is only needed on Windows
        if portable.ostype == "windows":
                def preinstall(self, pkgplan, orig):
                        """If the file exists, check if it is in use."""
                        if not orig:
                                return
                        path = orig.get_installed_path(pkgplan.image.get_root())
                        if os.path.isfile(path) and self.in_use(path):
                                raise api_errors.FileInUseException(path)

                def preremove(self, pkgplan):
                        path = self.get_installed_path(pkgplan.image.get_root())
                        if os.path.isfile(path) and self.in_use(path):
                                raise api_errors.FileInUseException(path)

                def in_use(self, path):
                        """Determine if a file is in use (locked) by trying
                        to rename the file to itself."""
                        try:
                                os.rename(path, path)
                        except OSError as err:
                                if err.errno != errno.EACCES:
                                        raise
                                return True
                        return False

        def __set_data(self, pkgplan):
                """Private helper function to set the data field of the
                action."""

                hash_attr, hash_attr_val, hash_func = \
                    digest.get_least_preferred_hash(self)

                retrieved = pkgplan.image.imageplan._retrieved
                retrieved.add(self.get_installed_path(
                    pkgplan.image.get_root()))
                if len(retrieved) > 50 or \
                    DebugValues['max-plan-execute-retrievals'] == 1:
                        raise api_errors.PlanExecutionError(retrieved)

                # This is an unexpected file retrieval, so the retrieved file
                # will be streamed directly from the source to the final
                # destination and will not be stored in the image download
                # cache.
                try:
                        pub = pkgplan.image.get_publisher(
                            pkgplan.destination_fmri.publisher)
                        data = pkgplan.image.transport.get_datastream(pub,
                            hash_attr_val)
                        return lambda: data
                finally:
                        pkgplan.image.cleanup_downloads()


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

                final_path = self.get_installed_path(pkgplan.image.get_root())

                # Don't allow installation through symlinks.
                self.fsobj_checkpath(pkgplan, final_path)

                if not os.path.exists(os.path.dirname(final_path)):
                        self.makedirs(os.path.dirname(final_path),
                            mode=misc.PKG_DIR_MODE,
                            fmri=pkgplan.destination_fmri)
                elif (not orig and not pkgplan.origin_fmri and
                    "preserve" in self.attrs and
                    self.attrs["preserve"] not in ("abandon",
                        "install-only") and os.path.isfile(final_path)):
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
                pres_type = self._check_preserve(orig, pkgplan)
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
                elif pres_type == "abandon":
                        return

                # If it is a directory (and not empty) then we should
                # salvage the contents.
                if os.path.exists(final_path) and \
                    not os.path.islink(final_path) and \
                    os.path.isdir(final_path):
                        try:
                                os.rmdir(final_path)
                        except OSError as e:
                                if e.errno == errno.ENOENT:
                                        pass
                                elif e.errno in (errno.EEXIST, errno.ENOTEMPTY):
                                        pkgplan.salvage(final_path)
                                elif e.errno != errno.EACCES:
                                        # this happens on Windows
                                        raise

                # XXX This needs to be modularized.
                if do_content and self.needsdata(orig, pkgplan):
                        tfilefd, temp = tempfile.mkstemp(dir=os.path.dirname(
                            final_path))
                        if not self.data:
                                # The state of the filesystem changed after the
                                # plan was prepared; attempt a one-off
                                # retrieval of the data.
                                self.data = self.__set_data(pkgplan)
                        stream = self.data()
                        tfile = os.fdopen(tfilefd, "wb")
                        try:
                                # Always verify using the most preferred hash
                                hash_attr, hash_val, hash_func  = \
                                    digest.get_preferred_hash(self)
                                shasum = misc.gunzip_from_stream(stream, tfile,
                                    hash_func)
                        except zlib.error as e:
                                raise ActionExecutionError(self,
                                    details=_("Error decompressing payload: "
                                        "{0}").format(
                                        " ".join([str(a) for a in e.args])),
                                        error=e)
                        finally:
                                tfile.close()
                                stream.close()

                        if shasum != hash_val:
                                raise ActionExecutionError(self,
                                    details=_("Action data hash verification "
                                    "failure: expected: {expected} computed: "
                                    "{actual} action: {action}").format(
                                        expected=hash_val,
                                        actual=shasum,
                                        action=self
                                   ))

                else:
                        temp = final_path

                try:
                        os.chmod(temp, mode)
                except OSError as e:
                        # If the file didn't exist, assume that's intentional,
                        # and drive on.
                        if e.errno != errno.ENOENT:
                                raise
                        else:
                                return

                try:
                        portable.chown(temp, owner, group)
                except OSError as e:
                        if e.errno != errno.EPERM:
                                raise

                # XXX There's a window where final_path doesn't exist, but we
                # probably don't care.
                if do_content and old_path:
                        try:
                                portable.rename(final_path, old_path)
                        except OSError as e:
                                if e.errno != errno.ENOENT:
                                        # Only care if file isn't gone already.
                                        raise

                # This is safe even if temp == final_path.
                try:
                        portable.rename(temp, final_path)
                except OSError as e:
                        raise api_errors.FileInUseException(final_path)

                # Handle timestamp if specified (and content was installed).
                if do_content and "timestamp" in self.attrs:
                        t = misc.timestamp_to_time(self.attrs["timestamp"])
                        try:
                                os.utime(final_path, (t, t))
                        except OSError as e:
                                if e.errno != errno.EACCES:
                                        raise

                                # On Windows, the time cannot be changed on a
                                # read-only file
                                os.chmod(final_path, stat.S_IRUSR|stat.S_IWUSR)
                                os.utime(final_path, (t, t))
                                os.chmod(final_path, mode)

                # Handle system attributes.
                sattr = self.attrs.get("sysattr")
                if sattr:
                        if isinstance(sattr, list):
                                sattr = ",".join(sattr)
                        sattrs = sattr.split(",")
                        if len(sattrs) == 1 and \
                            sattrs[0] not in portable.get_sysattr_dict():
                                # not a verbose attr, try as a compact attr seq
                                arg = sattrs[0]
                        else:
                                arg = sattrs

                        try:
                                portable.fsetattr(final_path, arg)
                        except OSError as e:
                                if e.errno != errno.EINVAL:
                                        raise
                                raise ActionExecutionError(self,
                                    details=_("System attributes are not "
                                    "supported on the target filesystem."))
                        except ValueError as e:
                                raise ActionExecutionError(self,
                                    details=_("Could not set system attributes "
                                    "'{attrlist}': {err}").format(
                                        attrlist=sattr,
                                        err=e
                                   ))

        def verify(self, img, **args):
                """Returns a tuple of lists of the form (errors, warnings,
                info).  The error list will be empty if the action has been
                correctly installed in the given image.

                In detail, this verifies that the file is present, and if
                the preserve attribute is not present, that the hashes
                and other attributes of the file match."""

                if self.attrs.get("preserve") == "abandon":
                        return [], [], []

                path = self.get_installed_path(img.get_root())

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
                        errors.append(_("Timestamp: {found} should be "
                            "{expected}").format(
                            found=misc.time_to_timestamp(lstat.st_mtime),
                            expected=self.attrs["timestamp"]))

                # avoid checking pkg.size if we have any content-hashes present;
                # different size files may have the same content-hash
                if "preserve" not in self.attrs and \
                    "pkg.size" in self.attrs and    \
                    not set(digest.RANKED_CONTENT_HASH_ATTRS).intersection(
                    set(self.attrs.keys())) and \
                    lstat.st_size != int(self.attrs["pkg.size"]):
                        errors.append(_("Size: {found:d} bytes should be "
                            "{expected:d}").format(found=lstat.st_size,
                            expected=int(self.attrs["pkg.size"])))

                if "preserve" in self.attrs:
                        if args["verbose"] == False or lstat is None:
                                return errors, warnings, info

                if args["forever"] != True:
                        return errors, warnings, info

                #
                # Check file contents. At the moment, the only content-hash
                # supported in pkg(7) is for ELF files, so this will need work
                # when additional content-hashes are added.
                #
                try:
                        # This is a generic mechanism, but only used for libc on
                        # x86, where the "best" version of libc is lofs-mounted
                        # on the canonical path, foiling the standard verify
                        # checks.
                        is_mtpt = self.attrs.get("mountpoint", "").lower() == "true"
                        content_hash = None
                        hash_error = None
                        content_hash_attr, content_hash_val, \
                            content_hash_func = \
                            digest.get_preferred_hash(self,
                                hash_type=pkg.digest.CONTENT_HASH)
                        if (content_hash_attr and have_content_hash and
                           not is_mtpt):
                                #
                                # It's possible for the elf module to
                                # throw while computing the hash,
                                # especially if the file is badly
                                # corrupted or truncated.
                                #
                                try:
                                        # On path, only calculate the
                                        # content hash that matches
                                        # the preferred one on the
                                        # action
                                        get_elfhash = \
                                            content_hash_attr == "elfhash"
                                        get_sha256 = (not get_elfhash and
                                            ":sha256:" in content_hash_val)
                                        get_sha512t_256 = (not get_elfhash and
                                            ":sha512t_256:" in content_hash_val)
                                        content_hash = elf.get_hashes(
                                            path, elfhash=get_elfhash,
                                            sha256=get_sha256,
                                            sha512t_256=get_sha512t_256
                                        )[content_hash_attr]

                                        if get_elfhash:
                                                content_hash = [content_hash]
                                except RuntimeError as e:
                                        errors.append(
                                            "ELF content hash: {0}".format(e))

                                if (content_hash is not None and
                                     content_hash_val not in content_hash):
                                        hash_error = _("ELF content hash: "
                                            "{found} "
                                            "should be {expected}").format(
                                            found=content_hash,
                                            expected=content_hash_val)

                        # If we failed to compute the content hash, or the
                        # content hash failed to verify, try the file hash.
                        # If the content hash fails to match but the file hash
                        # matches, it indicates that the content hash algorithm
                        # changed, since obviously the file hash is a superset
                        # of the content hash.
                        if (content_hash is None or hash_error) and not is_mtpt:
                                hash_attr, hash_val, hash_func = \
                                    digest.get_preferred_hash(self)
                                sha_hash, data = misc.get_data_digest(path,
                                    hash_func=hash_func)
                                if sha_hash != hash_val:
                                        # Prefer the content hash error message.
                                        if "preserve" in self.attrs:
                                                info.append(_(
                                                    "editable file has "
                                                    "been changed"))
                                        elif hash_error:
                                                errors.append(hash_error)
                                                self.replace_required = True
                                        else:
                                                errors.append(_("Hash: "
                                                    "{found} should be "
                                                    "{expected}").format(
                                                    found=sha_hash,
                                                    expected=hash_val))
                                                self.replace_required = True

                        # Check system attributes.
                        # Since some attributes like 'archive' or 'av_modified'
                        # are set automatically by the FS, it makes no sense to
                        # check for 1:1 matches. So we only check that the
                        # system attributes specified in the action are still
                        # set on the file.
                        sattr = self.attrs.get("sysattr", None)
                        if sattr:
                                if isinstance(sattr, list):
                                        sattr = ",".join(sattr)
                                sattrs = sattr.split(",")
                                if len(sattrs) == 1 and \
                                    sattrs[0] not in portable.get_sysattr_dict():
                                        # not a verbose attr, try as a compact
                                        set_attrs = portable.fgetattr(path,
                                            compact=True)
                                        sattrs = sattrs[0]
                                else:
                                        set_attrs = portable.fgetattr(path)

                                for a in sattrs:
                                        if a not in set_attrs:
                                                errors.append(
                                                    _("System attribute '{0}' "
                                                    "not set").format(a))

                except EnvironmentError as e:
                        if e.errno == errno.EACCES:
                                errors.append(_("Skipping: Permission Denied"))
                        else:
                                errors.append(_("Unexpected Error: {0}").format(
                                    e))
                except Exception as e:
                        errors.append(_("Unexpected Exception: {0}").format(e))

                return errors, warnings, info

        def _check_preserve(self, orig, pkgplan, orig_path=None):
                """Return the type of preservation needed for this action.

                Returns None if preservation is not defined by the action.
                Returns False if it is, but no preservation is necessary.
                Returns True for the normal preservation form.  Returns one of
                the strings 'renameold', 'renameold.update', 'renamenew',
                'legacy', or 'abandon' for each of the respective forms of
                preservation.
                """

                # If the logic in this function ever changes, all callers will
                # need to be updated to reflect how they interpret return
                # values.

                try:
                        pres_type = self.attrs["preserve"]
                except KeyError:
                        return

                # Should ultimately be conditioned on file type
                if "elfhash" in self.attrs:
                        # Don't allow preserve logic to be applied to elf files;
                        # if we ever stop tagging elf binaries with this
                        # attribute, this will need to be updated.
                        return

                if pres_type == "abandon":
                        return pres_type

                final_path = self.get_installed_path(pkgplan.image.get_root())

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

                # 'install-only' preservation has very specific semantics as
                # well; if there's an 'orig' or this is an initial install and
                # the file exists, we should not modify the file content.
                if pres_type == "install-only":
                        if orig or is_file:
                                return True
                        return False

                changed_hash = False
                if orig:
                        # We must use the same hash algorithm when comparing old
                        # and new actions. Look for the most-preferred common
                        # hash between old and new. Since the two actions may
                        # not share a common hash (in which case, we get a tuple
                        # of 'None' objects) we also need to know the preferred
                        # hash to use when examining the old action on its own.
                        common_hash_attr, common_hash_val, \
                            common_orig_hash_val, common_hash_func = \
                            digest.get_common_preferred_hash(self, orig)

                        hattr, orig_hash_val, orig_hash_func = \
                            digest.get_preferred_hash(orig)

                        if common_orig_hash_val and common_hash_val:
                                changed_hash = common_hash_val != common_orig_hash_val
                        else:
                                # we don't have a common hash, so we must treat
                                # this as a changed action
                                changed_hash = True

                        if pkgplan.destination_fmri and \
                            changed_hash and \
                            pkgplan.origin_fmri and \
                            pkgplan.destination_fmri.version < pkgplan.origin_fmri.version:
                                # Installed, preserved file is for a package
                                # newer than what will be installed. So check if
                                # the version on disk is different than what
                                # was originally delivered, and if so, preserve
                                # it.
                                if is_file:
                                        ihash, cdata = misc.get_data_digest(
                                            final_path,
                                            hash_func=orig_hash_func)
                                        if ihash != orig_hash_val:
                                                # .old is intentionally avoided
                                                # here to prevent accidental
                                                # collisions with the normal
                                                # install process.
                                                return "renameold.update"
                                return False

                if (orig and orig_path):
                        # Comparison will be based on a file being moved.
                        is_file = os.path.isfile(orig_path)

                # If the action has been marked with a preserve attribute, and
                # the file exists and has a content hash different from what the
                # system expected it to be, then we preserve the original file
                # in some way, depending on the value of preserve.
                if is_file:
                        # if we had an action installed, then we know what hash
                        # function was used to compute it's hash attribute.
                        if orig:
                                if not orig_path:
                                        orig_path = final_path
                                chash, cdata = misc.get_data_digest(orig_path,
                                    hash_func=orig_hash_func)
                        if not orig or chash != orig_hash_val:
                                if pres_type in ("renameold", "renamenew"):
                                        return pres_type
                                return True
                        elif not changed_hash and chash == orig_hash_val:
                                # If packaged content has not changed since last
                                # version and on-disk content matches the last
                                # version, preserve on-disk file.
                                return True

                return False

        # If we're not upgrading, or the file contents have changed,
        # retrieve the file and write it to a temporary location.
        # For files with content-hash attributes, only write the new file if the
        # content-hash changed.
        def needsdata(self, orig, pkgplan):
                if self.replace_required:
                        return True

                # import goes here to prevent circular import
                from pkg.client.imageconfig import CONTENT_UPDATE_POLICY

                use_content_hash = orig and pkgplan.image.cfg.get_policy_str(
                    CONTENT_UPDATE_POLICY) == "when-required"

                # If content update policy allows it, check for a common
                # preferred content hash.
                if use_content_hash:
                        content_hash_attr, content_hash_val, \
                        orig_content_hash_val, content_hash_func = \
                            digest.get_common_preferred_hash(
                                self, orig, hash_type=digest.CONTENT_HASH)

                hash_attr, hash_val, orig_hash_val, hash_func = \
                    digest.get_common_preferred_hash(self, orig)

                if not orig:
                        changed_hash = True
                elif orig and (orig_hash_val is None or
                    hash_val is None):
                        # we have no common hash so we have to treat this as a
                        # changed action
                        changed_hash = True
                else:
                        changed_hash = hash_val != orig_hash_val

                if (changed_hash and
                    (not use_content_hash or
                     content_hash_val != orig_content_hash_val)):
                        if ("preserve" not in self.attrs or
                            not pkgplan.origin_fmri or
                            (pkgplan.destination_fmri.version <
                            pkgplan.origin_fmri.version)):
                                return True
                elif orig:
                        # It's possible that the file content hasn't changed
                        # for an upgrade case, but the file is missing.  This
                        # ensures that for cases where the mode or some other
                        # attribute of the file has changed that the file will
                        # be installed.
                        path = self.get_installed_path(pkgplan.image.get_root())
                        if not os.path.isfile(path):
                                return True

                pres_type = self._check_preserve(orig, pkgplan)
                if pres_type not in (None, True, "abandon"):
                        # Preserved files only need data if they're being
                        # changed (e.g. "renameold", etc.).
                        return True

                return False

        def remove(self, pkgplan):
                path = self.get_installed_path(pkgplan.image.get_root())

                # Are we supposed to save this file to restore it elsewhere
                # or in another pkg? 'save_file' is set by the imageplan.
                save_file = self.attrs.get("save_file")
                if save_file:
                        # 'save_file' contains a tuple of (orig_name,
                        # remove_file).
                        remove = save_file[1]
                        self.save_file(pkgplan.image, path)
                        if remove != "true":
                                # File must be left in place (this file is
                                # likely overlaid and is moving).
                                return

                if self.attrs.get("preserve") in ("abandon", "install-only"):
                        return

                if not pkgplan.destination_fmri and \
                    self.attrs.get("preserve", "false").lower() != "false":
                        # Preserved files are salvaged if they have been
                        # modified since they were installed and this is
                        # not an upgrade.
                        try:
                                hash_attr, hash_val, hash_func  = \
                                    digest.get_preferred_hash(self)
                                ihash, cdata = misc.get_data_digest(path,
                                    hash_func=hash_func)
                                if ihash != hash_val:
                                        pkgplan.salvage(path)
                                        # Nothing more to do.
                                        return
                        except EnvironmentError as e:
                                if e.errno == errno.ENOENT:
                                        # Already gone; don't care.
                                        return
                                raise

                # Attempt to remove the file.
                rm_exc = None
                try:
                        self.remove_fsobj(pkgplan, path)
                        return
                except Exception as e:
                        if e.errno != errno.EACCES:
                                raise
                        rm_exc = e

                # There are only two likely reasons we couldn't remove the file;
                # either because the parent directory isn't writable, or
                # because the file is read-only and the OS isn't allowing its
                # removal.  Assume both and try making both the parent directory
                # and the file writable, removing the file, and finally
                # resetting the directory to its original mode.
                pdir = os.path.dirname(path)
                pmode = None
                try:
                        if pdir != pkgplan.image.get_root():
                                # Parent directory is not image root (e.g. '/').
                                ps = os.lstat(pdir)
                                pmode = ps.st_mode
                                os.chmod(pdir, misc.PKG_DIR_MODE)

                        # Make file writable and try removing it again; required
                        # on some operating systems or potentially for some
                        # filesystems?
                        os.chmod(path, stat.S_IWRITE|stat.S_IREAD)
                        self.remove_fsobj(pkgplan, path)
                except Exception as e:
                        # Raise new exception chained to old.
                        six.raise_from(e, rm_exc)
                finally:
                        # If parent directory wasn't image root, then assume
                        # mode needs reset.
                        if pmode is not None:
                                try:
                                        os.chmod(pdir, pmode)
                                except Exception as e:
                                        # Ignore failure to reset parent mode.
                                        pass

        def different(self, other, cmp_hash=True, pkgplan=None,
            cmp_unsigned=False):
                return generic.Action.different(self, other, cmp_hash=cmp_hash,
                    pkgplan=pkgplan, cmp_unsigned=cmp_unsigned)

        def generate_indices(self):
                """Generates the indices needed by the search dictionary.  See
                generic.py for a more detailed explanation."""

                index_list = [
                    # this entry shows the hash as the 'index', and the
                    # file path as the 'value' when showing results when the
                    # user has searched for the SHA-1 hash. This seems unusual,
                    # but maintains the behaviour we had for S11.
                    ("file", "content", self.hash, self.hash),
                    # This will result in a 2nd row of output when searching for
                    # the SHA-1 hash, but is consistent with our behaviour for
                    # the other hash attributes.
                    ("file", "hash", self.hash, None),
                    ("file", "basename", os.path.basename(self.attrs["path"]),
                    None),
                    ("file", "path", os.path.sep + self.attrs["path"], None)
                ]
                for attr in digest.DEFAULT_HASH_ATTRS:
                        # we already have an index entry for self.hash
                        if attr == "hash":
                                continue
                        hash = self.attrs.get(attr)
                        if hash is None:
                                continue
                        index_list.append(("file", attr, hash, None))
                return index_list

        def save_file(self, image, full_path):
                """Save a file for later installation (in same process
                invocation, if it exists)."""

                saved_name = image.temporary_file()
                try:
                        misc.copyfile(full_path, saved_name)
                except OSError as err:
                        if err.errno != errno.ENOENT:
                                raise

                        # If the file doesn't exist, it can't be saved, so
                        # be certain consumers of this information know there
                        # isn't an original to restore.
                        saved_name = None

                ip = image.imageplan
                ip.saved_files[self.attrs["save_file"][0]] = (self, saved_name)

        def restore_file(self, image):
                """restore a previously saved file; return cached action """

                ip = image.imageplan
                orig, saved_name = ip.saved_files[self.attrs["save_file"][0]]
                if saved_name is None:
                        # Nothing to restore; original file is missing.
                        return

                full_path = self.get_installed_path(image.get_root())
                assert not os.path.exists(full_path)

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

        if six.PY3:
                def __init__(self, data, **attrs):
                        _common._file_init(self, data, **attrs)

if six.PY2:
        FileAction.__init__ = types.MethodType(_common._file_init, None, FileAction)
