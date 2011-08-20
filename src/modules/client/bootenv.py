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

# Copyright (c) 2008, 2011, Oracle and/or its affiliates. All rights reserved.

import errno
import os
import tempfile

from pkg.client import global_settings
logger = global_settings.logger

import pkg.client.api_errors as api_errors
import pkg.misc as misc
import pkg.portable as portable
import pkg.pkgsubprocess as subprocess

# Since pkg(1) may be installed without libbe installed
# check for libbe and import it if it exists.
try:
        # First try importing using the new name (b172+)...
        import libbe as be
except ImportError:
        try:
                # ...then try importing using the old name (pre 172).
                import libbe_py as be
        except ImportError:
                # All recovery actions are disabled when libbe can't be
                # imported.
                pass

class BootEnv(object):

        """A BootEnv object is an object containing the logic for managing the
        recovery of image-modifying operations such as install, uninstall, and
        update.

        Recovery is only enabled for ZFS filesystems. Any operation attempted on
        UFS will not be handled by BootEnv.

        This class makes use of usr/lib/python*/vendor-packages/libbe.py as the
        python wrapper for interfacing with libbe.  Both libraries are delivered
        by the install/beadm package.  This package is not required for pkg(1)
        to operate successfully.  It is soft required, meaning if it exists the
        bootenv class will attempt to provide recovery support."""

        def __init__(self, img):
                self.be_name = None
                self.dataset = None
                self.be_name_clone = None
                self.be_name_clone_uuid = None
                self.clone_dir = None
                self.img = img
                self.is_live_BE = False
                self.is_valid = False
                self.snapshot_name = None
                # record current location of image root so we can remember
                # original source BE if we clone existing image
                self.root = self.img.get_root()
                rc = 0

                assert self.root != None

                # Need to find the name of the BE we're operating on in order
                # to create a snapshot and/or a clone of the BE.
                self.beList = self.get_be_list(raise_error=True)

                for i, beVals in enumerate(self.beList):
                        # pkg(1) expects a directory as the target of an
                        # operation. BootEnv needs to determine if this target
                        # directory maps to a BE. If a bogus directory is
                        # provided to pkg(1) via -R, then pkg(1) just updates
                        # '/' which also causes BootEnv to manage '/' as well.
                        # This should be fixed before this class is ever
                        # instantiated.

                        be_name = beVals.get("orig_be_name")

                        # If we're not looking at a boot env entry or an
                        # entry that is not mounted then continue.
                        if not be_name or not beVals.get("mounted"):
                                continue

                        # Check if we're operating on the live BE.
                        # If so it must also be active. If we are not
                        # operating on the live BE, then verify
                        # that the mountpoint of the BE matches
                        # the -R argument passed in by the user.
                        if self.root == '/':
                                if not beVals.get("active"):
                                        continue
                                else:
                                        self.is_live_BE = True
                        else:
                                if beVals.get("mountpoint") != self.root:
                                        continue

                        # Set the needed BE components so snapshots
                        # and clones can be managed.
                        self.be_name = be_name

                        self.dataset = beVals.get("dataset")

                        # Let libbe provide the snapshot name
                        err, snapshot_name = be.beCreateSnapshot(self.be_name)
                        self.clone_dir = tempfile.mkdtemp()

                        # Check first field for failure.
                        # 2nd field is the returned snapshot name
                        if err == 0:
                                self.snapshot_name = snapshot_name
                                # we require BootEnv to be initialised within
                                # the context of a history operation, i.e.
                                # after img.history.operation_name has been set.
                                img.history.operation_snapshot = snapshot_name
                        else:
                                logger.error(_("pkg: unable to create an auto "
                                    "snapshot. pkg recovery is disabled."))
                                raise RuntimeError, "recoveryDisabled"
                        self.is_valid = True
                        break

                else:
                        # We will get here if we don't find find any BE's. e.g
                        # if were are on UFS.
                        raise RuntimeError, "recoveryDisabled"

        def __get_new_be_name(self, suffix=None):
                """Create a new boot environment name."""

                new_bename = self.be_name
                if suffix:
                        new_bename += suffix
                base, sep, rev = new_bename.rpartition("-")
                if sep and rev.isdigit():
                        # The source BE has already been auto-named, so we need
                        # to bump the revision.  List all BEs, cycle through the
                        # names and find the one with the same basename as
                        # new_bename, and has the highest revision.  Then add
                        # one to it.  This means that gaps in the numbering will
                        # not be filled.
                        rev = int(rev)
                        maxrev = rev

                        for d in self.beList:
                                oben = d.get("orig_be_name", None)
                                if not oben:
                                        continue
                                nbase, sep, nrev = oben.rpartition("-")
                                if (not sep or nbase != base or
                                    not nrev.isdigit()):
                                        continue
                                maxrev = max(int(nrev), rev)
                else:
                        # If we didn't find the separator, or if the rightmost
                        # part wasn't an integer, then we just start with the
                        # original name.
                        base = new_bename
                        maxrev = 0

                good = False
                num = maxrev
                while not good:
                        new_bename = "-".join((base, str(num)))
                        for d in self.beList:
                                oben = d.get("orig_be_name", None)
                                if not oben:
                                        continue
                                if oben == new_bename:
                                        break
                        else:
                                good = True

                        num += 1
                return new_bename

        def __store_image_state(self):
                """Internal function used to preserve current image information
                and history state to be restored later with __reset_image_state
                if needed."""

                # Preserve the current history information and state so that if
                # boot environment operations fail, they can be written to the
                # original image root, etc.
                self.img.history.create_snapshot()

        def __reset_image_state(self, failure=False):
                """Internal function intended to be used to reset the image
                state, if needed, after the failure or success of boot
                environment operations."""

                if not self.img:
                        # Nothing to restore.
                        return

                if self.root != self.img.root:
                        if failure:
                                # Since the image root changed and the operation
                                # was not successful, restore the original
                                # history and state information so that it can
                                # be recorded in the original image root.  This
                                # needs to be done before the image root is
                                # reset since it might fail.
                                self.img.history.restore_snapshot()

                        self.img.history.discard_snapshot()

                        # After the completion of an operation that has changed
                        # the image root, it needs to be reset back to its
                        # original value so that the client will read and write
                        # information using the correct location (this is
                        # especially important for bootenv operations).
                        self.img.find_root(self.root)
                else:
                        self.img.history.discard_snapshot()

        def exists(self):

                """Return true if this object represents a valid BE."""

                return self.is_valid

        @staticmethod
        def libbe_exists():
                return True

        @staticmethod
        def check_verify():
                return hasattr(be, "beVerifyBEName")

        @staticmethod
        def split_be_entry(bee):
                name = bee.get("orig_be_name")
                return (name, bee.get("active"), bee.get("active_boot"),
                    bee.get("space_used"), bee.get("date"))

        @staticmethod
        def rename_be(orig_name, new_name):
                return be.beRename(orig_name, new_name)

        @staticmethod
        def destroy_be(be_name):
                return be.beDestroy(be_name, 1, True)

        @staticmethod
        def set_default_be(be_name):
                return be.beActivate(be_name)

        @staticmethod
        def check_be_name(be_name):
                try:
                        if be_name is None:
                                return

                        if be.beVerifyBEName(be_name) != 0:
                                raise api_errors.InvalidBENameException(be_name)

                        beList = BootEnv.get_be_list()

                        # If there is already a BE with the same name as
                        # be_name, then raise an exception.
                        if be_name in (be.get("orig_be_name") for be in beList):
                                raise api_errors.DuplicateBEName(be_name)
                except AttributeError:
                        raise api_errors.BENamingNotSupported(be_name)

        @staticmethod
        def get_be_list(raise_error=False):
                # Check for the old beList() API since pkg(1) can be
                # back published and live on a system without the 
                # latest libbe.
                rc = 0

                beVals = be.beList()
                # XXX temporary workaround for ON bug #7043482 (needed for
                # successful test suite runs on b166-b167).
                if portable.util.get_canonical_os_name() == "sunos":
                        for entry in os.listdir("/proc/self/path"):
                                try:
                                        int(entry)
                                except ValueError:
                                        # Only interested in file descriptors.
                                        continue

                                fpath = os.path.join("/proc/self/path", entry)
                                try:
                                        if os.readlink(fpath) == \
                                            "/etc/dev/cro_db":
                                                os.close(int(entry))
                                except OSError, e:
                                        if e.errno not in (errno.ENOENT,
                                            errno.EBADFD):
                                                raise

                if isinstance(beVals[0], int):
                        rc, beList = beVals
                else:
                        beList = beVals
                if not beList or rc != 0:
                        if raise_error:
                                # Happens e.g. in zones (for now) or live CD
                                # environment.
                                raise RuntimeError, "nobootenvironments"
                        beList = []

                return beList

        @staticmethod
        def get_be_name(path):
                """Looks for the name of the boot environment corresponding to
                an image root, returning name and uuid """
                beList = BootEnv.get_be_list()

                for be in beList:
                        be_name = be.get("orig_be_name")
                        be_uuid = be.get("uuid_str")

                        if not be_name or not be.get("mounted"):
                                continue

                        # Check if we're operating on the live BE.
                        # If so it must also be active. If we are not
                        # operating on the live BE, then verify
                        # that the mountpoint of the BE matches
                        # the path argument passed in by the user.
                        if path == '/':
                                if be.get("active"):
                                        return be_name, be_uuid
                        else:
                                if be.get("mountpoint") == path:
                                        return be_name, be_uuid
                return None, None

        @staticmethod
        def get_uuid_be_dic():
                """Return a dictionary of all boot environment names on the
                system, keyed by uuid"""
                beList = BootEnv.get_be_list()
                uuid_bes = {}
                for be in beList:
                        uuid_bes[be.get("uuid_str")] = be.get("orig_be_name")
                return uuid_bes

        @staticmethod
        def get_activated_be_name():
                try:
                        beList = BootEnv.get_be_list()

                        for be in beList:
                                if be.get("active_boot"):
                                        return be.get("orig_be_name")
                except AttributeError:
                        raise api_errors.BENamingNotSupported(be_name)

        @staticmethod
        def get_active_be_name():
                try:
                        beList = BootEnv.get_be_list()

                        for be in beList:
                                if be.get("active"):
                                        return be.get("orig_be_name")
                except AttributeError:
                        raise api_errors.BENamingNotSupported(be_name)

        def create_backup_be(self, be_name=None):
                """Create a backup BE if the BE being modified is the live one.

                'be_name' is an optional string indicating the name to use
                for the new backup BE."""

                self.check_be_name(be_name)

                if self.is_live_BE:
                        # Create a clone of the live BE, but do not mount or
                        # activate it.  Do nothing with the returned snapshot
                        # name that is taken of the clone during beCopy.
                        ret, be_name_clone, not_used = be.beCopy()
                        if ret != 0:
                                raise api_errors.UnableToCopyBE()

                        if not be_name:
                                be_name = self.__get_new_be_name(
                                    suffix="-backup-1")
                        ret = be.beRename(be_name_clone, be_name)
                        if ret != 0:
                                raise api_errors.UnableToRenameBE(
                                    be_name_clone, be_name)
                elif be_name is not None:
                        raise api_errors.BENameGivenOnDeadBE(be_name)

        def init_image_recovery(self, img, be_name=None):

                """Initialize for an update.
                        If a be_name is given, validate it.
                        If we're operating on a live BE then clone the
                        live BE and operate on the clone.
                        If we're operating on a non-live BE we use
                        the already created snapshot"""

                self.img = img

                if self.is_live_BE:
                        # Create a clone of the live BE and mount it.
                        self.destroy_snapshot()

                        self.check_be_name(be_name)

                        # Do nothing with the returned snapshot name
                        # that is taken of the clone during beCopy.
                        ret, self.be_name_clone, not_used = be.beCopy()
                        if ret != 0:
                                raise api_errors.UnableToCopyBE()
                        if be_name:
                                ret = be.beRename(self.be_name_clone, be_name)
                                if ret == 0:
                                        self.be_name_clone = be_name
                                else:
                                        raise api_errors.UnableToRenameBE(
                                            self.be_name_clone, be_name)
                        if be.beMount(self.be_name_clone, self.clone_dir) != 0:
                                raise api_errors.UnableToMountBE(
                                    self.be_name_clone, self.clone_dir)

                        # record the UUID of this cloned boot environment
                        not_used, self.be_name_clone_uuid = \
                            BootEnv.get_be_name(self.clone_dir)

                        # Set the image to our new mounted BE.
                        img.find_root(self.clone_dir, exact_match=True)
                elif be_name is not None:
                        raise api_errors.BENameGivenOnDeadBE(be_name)

        def update_boot_archive(self):
                """Rebuild the boot archive in the current image.
                Just report errors; failure of pkg command is not needed,
                and bootadm problems should be rare."""
                cmd = [
                    "/sbin/bootadm", "update-archive", "-R",
                    self.img.get_root()
                    ]

                try:
                        ret = subprocess.call(cmd,
                            stdout = open(os.devnull), stderr=subprocess.STDOUT)
                except OSError, e:
                        logger.error(_("pkg: A system error %(e)s was "
                            "caught executing %(cmd)s") % { "e": e,
                            "cmd": " ".join(cmd) })
                        return

                if ret:
                        logger.error(_("pkg: '%(cmd)s' failed. \nwith "
                            "a return code of %(ret)d.") % {
                            "cmd": " ".join(cmd), "ret": ret })
                    
                
        def activate_image(self, set_active=True):
                """Activate a clone of the BE being operated on.
                        If were operating on a non-live BE then
                        destroy the snapshot.

                'set_active' is an optional boolean indicating that the new
                BE (if created) should be set as the active one on next boot.
                """

                def activate_live_be():
                        if set_active and \
                            be.beActivate(self.be_name_clone) != 0:
                                logger.error(_("pkg: unable to activate %s") \
                                    % self.be_name_clone)
                                return

                        # Consider the last operation a success, and log it as
                        # ending here so that it will be recorded in the new
                        # image's history.
                        self.img.history.operation_new_be = self.be_name_clone
                        self.img.history.operation_new_be_uuid = self.be_name_clone_uuid
                        self.img.history.log_operation_end()

                        if be.beUnmount(self.be_name_clone) != 0:
                                logger.error(_("unable to unmount BE "
                                    "%(be_name)s mounted at %(be_path)s") % {
                                    "be_name": self.be_name_clone,
                                    "be_path": self.clone_dir })
                                return

                        os.rmdir(self.clone_dir)

                        if set_active:
                                logger.info(_("""
A clone of %(be_name)s exists and has been updated and activated.
On the next boot the Boot Environment %(be_name_clone)s will be
mounted on '/'.  Reboot when ready to switch to this updated BE.
""") % self.__dict__)
                        else:
                                logger.info(_("""
A clone of %(be_name)s exists and has been updated.  To set the
new BE as the active one on next boot, execute the following
command as a privileged user and reboot when ready to switch to
the updated BE:

beadm activate %(be_name_clone)s
""") % self.__dict__)

                def activate_be():
                        # Delete the snapshot that was taken before we
                        # updated the image and the boot archive.
                        logger.info(_("%s has been updated successfully") %
                            self.be_name)

                        os.rmdir(self.clone_dir)
                        self.destroy_snapshot()
                        self.img.history.operation_snapshot = None

                self.__store_image_state()

                relock = False
                if self.img.locked:
                        # This is necessary since the lock will
                        # prevent the boot environment from being
                        # unmounted during activation.  Normally,
                        # locking for the image is handled
                        # automatically.
                        relock = True
                        self.img.unlock()

                caught_exception = None

                try:
                        if self.is_live_BE:
                                activate_live_be()
                        else:
                                activate_be()
                except Exception, e:
                        caught_exception = e
                        if relock:
                                # Re-lock be image.
                                relock = False
                                self.img.lock()

                self.__reset_image_state(failure=caught_exception)
                if relock:
                        # Activation was successful so the be image was
                        # unmounted and the parent image must be re-locked.
                        self.img.lock()

                if caught_exception:
                        self.img.history.log_operation_error(error=e)
                        raise caught_exception

        def restore_image(self):
                """Restore a failed update attempt."""

                self.__reset_image_state(failure=True)

                # Leave the clone around for debugging purposes if we're
                # operating on the live BE.
                if self.is_live_BE:
                        logger.error(_(" The running system has not been "
                            "modified. Modifications were only made to a clone "
                            "of the running system.  This clone is mounted at "
                            "%s should you wish to inspect it.") % \
                            self.clone_dir)

                else:
                        # Rollback and destroy the snapshot.
                        try:
                                if be.beRollback(self.be_name,
                                    self.snapshot_name) != 0:
                                        logger.error(_("pkg: unable to "
                                            "rollback BE %s and restore "
                                            "image") % self.be_name)

                                self.destroy_snapshot()
                                os.rmdir(self.clone_dir)
                        except Exception, e:
                                self.img.history.log_operation_error(error=e)
                                raise e

                        logger.error(_("%s failed to be updated. No changes "
                            "have been made to %s.") % (self.be_name,
                            self.be_name))

        def destroy_snapshot(self):

                """Destroy a snapshot of the BE being operated on.
                        Note that this will destroy the last created
                        snapshot and does not support destroying
                        multiple snapshots. Create another instance of
                        BootEnv to manage multiple snapshots."""

                if be.beDestroySnapshot(self.be_name, self.snapshot_name) != 0:
                        logger.error(_("pkg: unable to destroy snapshot "
                            "%s") % self.snapshot_name)

        def restore_install_uninstall(self):

                """Restore a failed install or uninstall attempt.
                        Clone the snapshot, mount the BE and
                        notify user of its existence. Rollback
                        if not operating on a live BE"""

                if self.is_live_BE:
                        # Create a new BE based on the previously taken
                        # snapshot.

                        ret, self.be_name_clone, not_used = \
                            be.beCopy(None, self.be_name, self.snapshot_name)
                        if ret != 0:
                                # If the above beCopy() failed we will try it
                                # without expecting the BE clone name to be
                                # returned by libbe. We do this in case an old
                                # version of libbe is on a system with
                                # a new version of pkg.
                                self.be_name_clone = self.be_name + "_" + \
                                    self.snapshot_name

                                ret, not_used, not_used2 = \
                                    be.beCopy(self.be_name_clone, \
                                    self.be_name, self.snapshot_name)
                                if ret != 0:
                                        logger.error(_("pkg: unable to create "
                                            "BE %s") % self.be_name_clone)
                                        return

                        if be.beMount(self.be_name_clone, self.clone_dir) != 0:
                                logger.error(_("pkg: unable to mount BE "
                                    "%(name)s on %(clone_dir)s") % {
                                    "name": self.be_name_clone,
                                    "clone_dir": self.clone_dir })
                                return

                        logger.error(_("The Boot Environment %(name)s failed "
                            "to be updated. A snapshot was taken before the "
                            "failed attempt and is mounted here %(clone_dir)s. "
                            "Use 'beadm unmount %(clone_name)s' and then "
                            "'beadm activate %(clone_name)s' if you wish to "
                            "boot to this BE.") % { "name": self.be_name,
                            "clone_dir": self.clone_dir,
                            "clone_name": self.be_name_clone })
                else:
                        if be.beRollback(self.be_name, self.snapshot_name) != 0:
                                logger.error("pkg: unable to rollback BE "
                                    "%s" % self.be_name)

                        self.destroy_snapshot()

                        logger.error(_("The Boot Environment %s failed to be "
                            "updated. A snapshot was taken before the failed "
                            "attempt and has been restored so no changes have "
                            "been made to %s.") % (self.be_name, self.be_name))

        def activate_install_uninstall(self):
                """Activate an install/uninstall attempt. Which just means
                        destroy the snapshot for the live and non-live case."""

                self.destroy_snapshot()

class BootEnvNull(object):

        """BootEnvNull is a class that gets used when libbe doesn't exist."""

        def __init__(self, img):
                pass

        @staticmethod
        def update_boot_archive():
                pass

        @staticmethod
        def exists():
                return False

        @staticmethod
        def libbe_exists():
                return False

        @staticmethod
        def check_verify():
                return False

        @staticmethod
        def split_be_entry(bee):
                return None

        @staticmethod
        def rename_be(orig_name, new_name):
	        pass

        @staticmethod
        def destroy_be(be_name):
	        pass

        @staticmethod
        def set_default_be(be_name):
                pass

        @staticmethod
        def check_be_name(be_name):
                if be_name:
                        raise api_errors.BENamingNotSupported(be_name)

        @staticmethod
        def get_be_list():
                pass

        @staticmethod
        def get_be_name(path):
                return None, None

        @staticmethod
        def get_uuid_be_dic():
                return misc.EmptyDict

        @staticmethod
        def get_activated_be_name():
                pass

        @staticmethod
        def get_active_be_name():
                pass

        @staticmethod
        def create_backup_be(be_name=None):
                if be_name is not None:
                        raise api_errors.BENameGivenOnDeadBE(be_name)

        @staticmethod
        def init_image_recovery(img, be_name=None):
                if be_name is not None:
                        raise api_errors.BENameGivenOnDeadBE(be_name)

        @staticmethod
        def activate_image():
                pass

        @staticmethod
        def restore_image():
                pass

        @staticmethod
        def destroy_snapshot():
                pass

        @staticmethod
        def restore_install_uninstall():
                pass

        @staticmethod
        def activate_install_uninstall():
                pass

if "be" not in locals():
        BootEnv = BootEnvNull
