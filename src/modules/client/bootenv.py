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

# Copyright (c) 2008, 2021, Oracle and/or its affiliates.

import errno
import os
import shutil
import tempfile

from pkg.client import global_settings
logger = global_settings.logger

import pkg.client.api_errors as api_errors
import pkg.misc as misc
import pkg.portable as portable
import pkg.pkgsubprocess as subprocess


# pkg(1) can be installed and used without any BE management module.
# However, in order to provide recovery feature,
# it will try to use the BE management module if it exists.
# We will first try to import the pybemgmt module, which is only
# available in Solaris 11.4 onwards.  If it's not found, we will
# also attempt to use the old libbe module, if it exists.
try:
        # First, try importing the pybemgmt module.
        import bemgmt
        from bemgmt.be_errors import BeFmriError, BeNameError, \
            BeNotFoundError, BeMgmtError, BeMgmtOpError
except ImportError:
        # Try importing older libbe
        try:
                import libbe as be
        except ImportError:
                try:
                        # try importing using libbe module's old name (pre 172)
                        import libbe_py as be
                except ImportError:
                        # All recovery actions are disabled when libbe can't
                        # be imported.
                        pass

class GenericBootEnv(object):
        """This class contains common functions used by both bemgmt module
        and the older pylibbe module.
        """
        def __init__(self, img, progress_tracker=None):
                self.be_name = None
                self.dataset = None
                self.be_name_clone = None
                self.be_name_clone_uuid = None
                self.clone_dir = None
                self.img = img
                self.is_live_BE = False
                self.is_valid = False
                self.snapshot_name = None
                self.progress_tracker = progress_tracker

                # record current location of image root so we can remember
                # original source BE if we clone existing image
                self.root = self.img.get_root()
                rc = 0

                assert self.root != None

        def _store_image_state(self):
                """Internal function used to preserve current image information
                and history state to be restored later with _reset_image_state
                if needed."""

                # Preserve the current history information and state so that if
                # boot environment operations fail, they can be written to the
                # original image root, etc.
                self.img.history.create_snapshot()

        def _reset_image_state(self, failure=False):
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
                except OSError as e:
                        logger.error(_("pkg: A system error {e} was "
                            "caught executing {cmd}").format(e=e,
                            cmd=" ".join(cmd)))
                        return

                if ret:
                        logger.error(_("pkg: '{cmd}' failed. \nwith "
                            "a return code of {ret:d}.").format(
                            cmd=" ".join(cmd), ret=ret))

        def activate_install_uninstall(self):
                """Activate an install/uninstall attempt. Which just means
                destroy the snapshot for the live and non-live case."""

                self.destroy_snapshot()


class BeadmV2BootEnv(GenericBootEnv):
        """A BeadmV2BootEnv object is an object containing the
        logic for managing the recovery of image-modifying operations such
        as install, uninstall, and update.

        This class makes use of BE management interfaces from
        usr/lib/python*/vendor-packages/bemgmt. The BE management module is
        delivered by the pkg:/system/boot-environment-utilities package.
        This package is not required for pkg(1) to operate successfully.
        It is soft required, meaning if it exists the bootenv class will
        attempt to provide recovery support."""

        def __init__(self, img, progress_tracker=None):

                GenericBootEnv.__init__(self, img, progress_tracker)

                self.bemgr = bemgmt.BEManager(logger=logger)
                self.img_be = None
                self.be_clone = None
                try:
                    self.beList = self.bemgr.list()
                except BeMgmtOpError:
                        # Unable to get the list of BEs
                        if portable.osname == "sunos":
                                raise RuntimeError("recoveryDisabled")

                # Need to find the name of the BE we're operating on in order
                # to create a snapshot and/or a clone of the BE.
                for be in self.beList:
                        if not be.mounted:
                                continue

                        # Check if we're operating on the live BE.
                        # If so it must also be active. If we are not
                        # operating on the live BE, then verify
                        # that the mountpoint of the BE matches
                        # the -R argument passed in by the user.
                        if self.root == '/':
                                if not be.active:
                                        continue
                                else:
                                        self.is_live_BE = True
                        else:
                                if be.mountpoint != self.root:
                                        continue

                        # Set the needed BE components so snapshots
                        # and clones can be managed.
                        self.be_name = be.name
                        self.dataset = be.root_dataset.name
                        self.img_be = be

                        try:
                                # Take a snapshot of the BE being operated on.
                                # Let BE management generate a snapshot name.
                                self.snapshot_name = self.bemgr.snapshot(
                                    fmri=self.img_be.fmri)
                                img.history.operation_snapshot = \
                                    self.snapshot_name
                        except Exception as ex:
                                logger.error(_("pkg: unable to create an auto "
                                    "snapshot. pkg recovery is disabled."))
                                raise RuntimeError("recoveryDisabled")

                        self.clone_dir = tempfile.mkdtemp()
                        self.is_valid = True

                        break

                else:
                        # We will get here if we don't find find any BE's. e.g
                        # if were are on UFS.
                        raise RuntimeError("recoveryDisabled")

        @staticmethod
        def libbe_exists():
                return True

        @staticmethod
        def check_verify():
                # The bemgmt module always has the validate_bename() function.
                return True

        @staticmethod
        def split_be_entry(bee):
                return (bee.name, bee.activate, bee.active_on_boot,
                        bee.space_used, bee.creation)

        @staticmethod
        def copy_be(src_be_name, dst_be_name):
                bemgr = bemgmt.BEManager(logger=logger)
                try:
                        bemgr.copy(dst_be_fmri=dst_be_name,
                                   src_be_fmri=src_be_name)
                except BeMgmtError:
                        raise api_errors.UnableToCopyBE()

        @staticmethod
        def rename_be(orig_name, new_name):
                bemgr = bemgmt.BEManager(logger=logger)
                bemgr.rename(orig_name, new_name)

        @staticmethod
        def destroy_be(be_name):
                bemgr = bemgmt.BEManager(logger=logger)
                return bemgr.destroy(be_name, destroy_snaps=True,
                                     force_umount=True)

        @staticmethod
        def cleanup_be(be_name):
                ''' Force unmount and destroy BE.  Ignore all errors '''

                bemgr = bemgmt.BEManager(logger=logger)
                try:
                        be_obj = bemgr.list(fmri=be_name)
                        be_obj = be_obj[0]
                except Exception as e:
                        # BE is not found.
                        return

                try:
                        mounted = be_obj.mounted
                        mountpoint = be_obj.mountpoint
                        bemgr.destroy(be_name, destroy_snaps=True,
                            force_umount=True)
                        if mounted:
                                shutil.rmtree(mountpoint,
                                    ignore_errors=True)
                except Exception as e:
                    pass

        @staticmethod
        def mount_be(be_name, mntpt, include_bpool=False):
                bemgr = bemgmt.BEManager(logger=logger)
                bemgr.mount(fmri=be_name, mountpoint=mntpt,
                            mount_bpool=include_bpool)

        @staticmethod
        def unmount_be(be_name, force=False):
                bemgr = bemgmt.BEManager(logger=logger)
                bemgr.unmount(fmri=be_name, force=force)

        @staticmethod
        def set_default_be(be_name):
                bemgr = bemgmt.BEManager(logger=logger)
                return bemgr.activate(be_name)

        @staticmethod
        def check_be_name(be_name):
                try:
                        if be_name is None:
                                return

                        bemgr = bemgmt.BEManager(logger=logger)
                        bemgr.validate_bename(be_name)

                        # Check whether there's already a BE or ZBE with
                        # the given name.
                        be_obj = bemgr.be_exists(be_name)
                except (BeFmriError, BeNameError):
                        raise api_errors.InvalidBENameException(be_name)
                except BeMgmtError:
                        raise api_errors.BENamingNotSupported(be_name)

                if be_obj:
                        # A BE or Zone BE with the given be_name exists.
                        zonename = None
                        if be_obj.parent_uuid:
                                zonename = be_obj.be_group.name
                        raise api_errors.DuplicateBEName(
                            be_name, zonename=zonename)

        @staticmethod
        def get_be_list(raise_error=False):
                # This check enables the test suite to run much more quickly.
                # It is necessary because pkg5unittest (eventually) imports this
                # module before the environment is sanitized.
                if "PKG_NO_LIVE_ROOT" in os.environ:
                        return BootEnvNull.get_be_list()

                bemgr = bemgmt.BEManager(logger=logger)
                try:
                    beList = bemgr.list()
                except Exception:
                    return []
                return (beList)

        @staticmethod
        def get_be_names():
                """Return a list of BE names."""
                return [
                    be.name for be in BeadmV2BootEnv.get_be_list() if be.name
                ]

        @staticmethod
        def get_be_name(path):
                """Looks for the name of the boot environment corresponding to
                an image root, returning name and uuid """

                # This check enables the test suite to run much more quickly.
                # The bemgr.list() call in the bemgmt module scans the
                # whole system, and might take a long time depending
                # on how many BEs are there on the system.
                #
                # This is necessary because pkg5unittest (eventually) imports
                # the module before the environment is sanitized.
                if "PKG_NO_LIVE_ROOT" in os.environ:
                        return BootEnvNull.get_be_name(path)

                bemgr = bemgmt.BEManager(logger=logger)
                try:
                    beList = bemgr.list()
                except Exception:
                    # Unable to get the list of BEs.
                    return None, None

                for be in beList:
                        if not be.mounted:
                            continue

                        # Check if we're operating on the live BE.
                        # If so it must also be active. If we are not
                        # operating on the live BE, then verify
                        # that the mountpoint of the BE matches
                        # the path argument passed in by the user.
                        if path == '/':
                                if be.active:
                                        return be.name, be.uuid
                        else:
                                if be.mountpoint == path:
                                        return be.name, be.uuid
                return None, None

        @staticmethod
        def get_uuid_be_dic():
                """Return a dictionary of all boot environment names on the
                system, keyed by uuid"""
                bemgr = bemgmt.BEManager(logger=logger)
                try:
                    beList = bemgr.list()
                except Exception:
                    return {}

                uuid_bes = {}
                for be in beList:
                        uuid_bes[be.uuid] = be.name
                return uuid_bes

        @staticmethod
        def get_activated_be_name():
                try:
                        bemgr = bemgmt.BEManager(logger=logger)
                        be_obj = bemgr.get_active_on_boot_be()
                        return (be_obj.name)
                except Exception:
                        raise api_errors.BENamingNotSupported("")

        @staticmethod
        def get_active_be_name():
                try:
                        bemgr = bemgmt.BEManager(logger=logger)
                        be_obj = bemgr.get_active_be()
                        return (be_obj.name)
                except Exception:
                        raise api_errors.BENamingNotSupported("")


        def create_backup_be(self, be_name=None):
                """Create a backup BE if the BE being modified is the live one.

                'be_name' is an optional string indicating the name to use
                for the new backup BE."""

                if self.is_live_BE:
                        if not be_name:
                                suffix = "-backup"
                        else:
                                suffix = None

                        # Create a clone of the live BE, but do not mount or
                        # activate it.
                        try:
                                self.bemgr.copy(dst_be_fmri=be_name,
                                                dst_bename_suffix=suffix)
                        except Exception as ex:
                                raise api_errors.UnableToCopyBE()

                elif be_name is not None:
                        raise api_errors.BENameGivenOnDeadBE(be_name)

        def init_image_recovery(self, img, be_name=None):
                """Initialize for an update.  If we're operating on
                a live BE then clone the live BE and operate on the
                clone.  If we're operating on a non-live BE we use
                the already created snapshot. Validation of the
                be_name is performed at the api level."""

                self.img = img
                if not self.is_live_BE and be_name is not None:
                        raise api_errors.BENameGivenOnDeadBE(be_name)

                # If the plan discovered a suggested BE name and we didn't 
                # get one from the CLI/API use the one from the plan.
                # First checking that it is valid and not already in use.
                # If it is in use already we fallback to letting bemgr.copy()
                # pick the new value for be_name.
                if img.imageplan.pd._be_name and not be_name:
                        be_name = img.imageplan.pd._be_name

                # Create a clone of the live BE and mount it.
                self.destroy_snapshot()

                try:
                        self.be_clone = self.bemgr.copy(
                            dst_be_fmri=be_name)
                        self.be_name_clone = self.be_clone.fmri
                except Exception:
                        raise api_errors.UnableToCopyBE()

                try:
                        self.bemgr.mount(fmri=self.be_clone.fmri,
                                         mountpoint=self.clone_dir)
                except Exception:
                        raise api_errors.UnableToMountBE(
                            self.be_clone.name, self.clone_dir)

                # record the UUID of this cloned boot environment
                self.be_name_clone_uuid = self.be_clone.uuid

                # Set the image to our new mounted BE.
                img.find_root(self.clone_dir, exact_match=True)

        def activate_image(self, set_active=True):
                """Activate a clone of the BE being operated on.
                If we are operating on a non-live BE then destroy the snapshot.

                'set_active' is an optional boolean indicating that the new
                BE (if created) should be set as the active one on next boot.
                """

                def activate_live_be():
                        if set_active:
                            try:
                                    self.bemgr.activate(fmri=self.be_clone.fmri)
                            except Exception:
                                    logger.error(_("pkg: unable to activate "
                                        "{0}").format(self.be_clone.name))
                                    return

                        # Consider the last operation a success, and log it as
                        # ending here so that it will be recorded in the new
                        # image's history.
                        self.img.history.operation_new_be = self.be_clone.name
                        self.img.history.operation_new_be_uuid = \
                            self.be_clone.uuid
                        self.img.history.log_operation_end(release_notes=
			    self.img.imageplan.pd.release_notes_name)

                        try:
                                self.bemgr.unmount(fmri=self.be_clone.fmri)
                        except Exception as ex:
                                logger.error(_("unable to unmount BE "
                                    "{be_name} mounted at {be_path}").format(
                                    be_name=self.be_clone.name,
                                    be_path=self.clone_dir))
                                return

                        os.rmdir(self.clone_dir)

                        if set_active:
                                logger.info(_("""
A clone of {be_name} exists and has been updated and activated.
On the next boot the Boot Environment {be_name_clone} will be
mounted on '/'.  Reboot when ready to switch to this updated BE.
""").format(**self.__dict__))
                        else:
                                logger.info(_("""
A clone of {be_name} exists and has been updated.  To set the
new BE as the active one on next boot, execute the following
command as a privileged user and reboot when ready to switch to
the updated BE:

beadm activate {be_name_clone}
""").format(**self.__dict__))

                def activate_be():
                        # Delete the snapshot that was taken before we
                        # updated the image and the boot archive.
                        logger.info(_("{0} has been updated "
                            "successfully").format(self.be_name))

                        os.rmdir(self.clone_dir)
                        self.destroy_snapshot()
                        self.img.history.operation_snapshot = None

                self._store_image_state()

                # Ensure cache is flushed before activating and unmounting BE.
                self.img.cleanup_cached_content(progtrack=self.progress_tracker)

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
                except Exception as e:
                        caught_exception = e
                        if relock:
                                # Re-lock be image.
                                relock = False
                                self.img.lock()

                self._reset_image_state(failure=caught_exception)
                if relock:
                        # Activation was successful so the be image was
                        # unmounted and the parent image must be re-locked.
                        self.img.lock()

                if caught_exception:
                        self.img.history.log_operation_error(error=e)
                        raise caught_exception

        def restore_image(self):
                """Restore a failed update attempt."""

                # flush() is necessary here so that the warnings get printed
                # on a new line.
                if self.progress_tracker:
                        self.progress_tracker.flush()

                self._reset_image_state(failure=True)

                # Leave the clone around for debugging purposes if we're
                # operating on the live BE.
                if self.is_live_BE:
                        logger.error(_("The running system has not been "
                            "modified. Modifications were only made to a clone "
                            "({0}) of the running system.  This clone is "
                            "mounted at {1} should you wish to inspect "
                            "it.").format(
                            self.be_name_clone, self.clone_dir))

                else:
                        # Rollback and destroy the snapshot.
                        try:
                                try:
                                        self.bemgr.rollback(self.snapshot_fmri)
                                except Exception:
                                        logger.error(_("pkg: unable to "
                                            "rollback BE {0} and restore "
                                            "image").format(self.be_name))

                                self.destroy_snapshot()
                                os.rmdir(self.clone_dir)
                        except Exception as e:
                                self.img.history.log_operation_error(error=e)
                                raise e

                        logger.error(_("{bename} failed to be updated. No "
                            "changes have been made to {bename}.").format(
                            bename=self.be_name))

        def destroy_snapshot(self):
                """Destroy a snapshot of the BE being operated on.
                Note that this will destroy the last created
                snapshot and does not support destroying
                multiple snapshots. Create another instance of
                BootEnv to manage multiple snapshots."""

                try:
                        self.bemgr.destroy(fmri=self.snapshot_name)
                except IOError:
                        logger.error("Got IOError from bemgr.destroy %s",
                                     self.snapshot_name)
                except Exception:
                        logger.error(_("pkg: unable to destroy snapshot "
                            "{0}").format(self.snapshot_name))

        def restore_install_uninstall(self):
                """Restore a failed install or uninstall attempt.
                Clone the snapshot, mount the BE and notify user of its
                existence. Rollback if not operating on a live BE. """

                # flush() is necessary here so that the warnings get printed
                # on a new line.
                if self.progress_tracker:
                        self.progress_tracker.flush()

                if self.is_live_BE:
                        # Create a new BE based on the previously taken
                        # snapshot.

                        try:
                                self.be_clone = self.bemgr.copy(
                                    src_be_fmri=self.snapshot_name)
                        except Exception:
                                logger.error(_("pkg: unable to create "
                                    "BE from snapshot {0}").format(
                                    self.snapshot_name))
                                return

                        try:
                                self.bemgr.mount(fmri=self.be_clone.fmri,
                                                 mountpoint=self.clone_dir)
                        except Exception:
                                logger.error(_("pkg: unable to mount BE "
                                    "{name} on {clone_dir}").format(
                                    name=self.be_clone.name,
                                    clone_dir=self.clone_dir))
                                return

                        logger.error(_("The Boot Environment {name} failed "
                            "to be updated. A snapshot was taken before the "
                            "failed attempt and is mounted here {clone_dir}. "
                            "Use 'beadm unmount {clone_name}' and then "
                            "'beadm activate {clone_name}' if you wish to "
                            "boot to this BE.").format(name=self.be_name,
                            clone_dir=self.clone_dir,
                            clone_name=self.be_clone.name))
                else:

                        try:
                                self.bemgr.rollback(
                                    snapshot_fmri=self.snapshot_name)
                        except Exception:
                                logger.error("pkg: unable to rollback BE "
                                    "{0}".format(self.be_name))

                        self.destroy_snapshot()

                        logger.error(_("The Boot Environment {bename} failed "
                            "to be updated. A snapshot was taken before the "
                            "failed attempt and has been restored so no "
                            "changes have been made to {bename}.").format(
                            bename=self.be_name))


class BeadmV1BootEnv(GenericBootEnv):
        """A BeadmV1BootEnv object is an object containing the
        logic for managing the recovery of image-modifying operations such
        as install, uninstall, and update.

        Recovery is only enabled for ZFS filesystems. Any operation attempted
        on UFS will not be handled by BootEnv.

        This class makes use of usr/lib/python*/vendor-packages/libbe.py
        as the python wrapper for interfacing with libbe.  Both libraries are
        delivered by the pkg:/system/boot-environment-utilities package.
        This package is not required for pkg(1) to operate successfully.
        It is soft required, meaning if it exists the bootenv class will
        attempt to provide recovery support."""

        def __init__(self, img, progress_tracker=None):

                GenericBootEnv.__init__(self, img, progress_tracker)

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
                                raise RuntimeError("recoveryDisabled")
                        self.is_valid = True
                        break

                else:
                        # We will get here if we don't find find any BE's. e.g
                        # if we are on UFS.
                        raise RuntimeError("recoveryDisabled")

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
        def copy_be(src_be_name, dst_be_name):
                ret, be_name_clone, not_used = be.beCopy(
                    dst_bename=dst_be_name,
                    src_bename=src_be_name)
                if ret != 0:
                        raise api_errors.UnableToCopyBE()

        @staticmethod
        def rename_be(orig_name, new_name):
                return be.beRename(orig_name, new_name)

        @staticmethod
        def destroy_be(be_name):
                return be.beDestroy(be_name, 1, True)

        @staticmethod
        def cleanup_be(be_name):
                be_list = BootEnv.get_be_list()
                for elem in be_list:
                        if "orig_be_name" in elem and be_name == \
                            elem["orig_be_name"]:
                                # Force unmount the be and destroy it.
                                # Ignore errors.
                                try:
                                        if elem.get("mounted"):
                                                BootEnv.unmount_be(
                                                    be_name, force=True)
                                                shutil.rmtree(elem.get(
                                                    "mountpoint"),
                                                    ignore_errors=True)
                                        BootEnv.destroy_be(
                                            be_name)
                                except Exception as e:
                                            pass
                                break

        @staticmethod
        def mount_be(be_name, mntpt, include_bpool=False):
                return be.beMount(be_name, mntpt, include_bpool=include_bpool)

        @staticmethod
        def unmount_be(be_name, force=False):
                return be.beUnmount(be_name, force=force)

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
                # This check enables the test suite to run much more quickly.
                # It is necessary because pkg5unittest (eventually) imports this
                # module before the environment is sanitized.
                if "PKG_NO_LIVE_ROOT" in os.environ:
                        return BootEnvNull.get_be_list()
                # Check for the old beList() API since pkg(1) can be
                # back published and live on a system without the
                # latest libbe.
                rc = 0

                beVals = be.beList()
                if isinstance(beVals[0], int):
                        rc, beList = beVals
                else:
                        beList = beVals
                if not beList or rc != 0:
                        if raise_error:
                                # Happens e.g. in zones (for now) or live CD
                                # environment.
                                raise RuntimeError("nobootenvironments")
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
        def get_be_names():
                """Return a list of BE names."""
                return [
                    be["orig_be_name"] for be in BeadmV1BootEnv.get_be_list()
                    if "orig_be_name" in be
                ]

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
                                # don't look at active but unbootable BEs.
                                # (happens in zones when we have ZBEs
                                # associated with other global zone BEs.)
                                if be.get("active_unbootable", False):
                                        continue
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
                except OSError as e:
                        logger.error(_("pkg: A system error {e} was "
                            "caught executing {cmd}").format(e=e,
                            cmd=" ".join(cmd)))
                        return

                if ret:
                        logger.error(_("pkg: '{cmd}' failed. \nwith "
                            "a return code of {ret:d}.").format(
                            cmd=" ".join(cmd), ret=ret))


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
                                logger.error(_("pkg: unable to activate "
                                    "{0}").format(self.be_name_clone))
                                return

                        # Consider the last operation a success, and log it as
                        # ending here so that it will be recorded in the new
                        # image's history.
                        self.img.history.operation_new_be = self.be_name_clone
                        self.img.history.operation_new_be_uuid = self.be_name_clone_uuid
                        self.img.history.log_operation_end(release_notes=
			    self.img.imageplan.pd.release_notes_name)

                        if be.beUnmount(self.be_name_clone) != 0:
                                logger.error(_("unable to unmount BE "
                                    "{be_name} mounted at {be_path}").format(
                                    be_name=self.be_name_clone,
                                    be_path=self.clone_dir))
                                return

                        os.rmdir(self.clone_dir)

                        if set_active:
                                logger.info(_("""
A clone of {be_name} exists and has been updated and activated.
On the next boot the Boot Environment {be_name_clone} will be
mounted on '/'.  Reboot when ready to switch to this updated BE.
""").format(**self.__dict__))
                        else:
                                logger.info(_("""
A clone of {be_name} exists and has been updated.  To set the
new BE as the active one on next boot, execute the following
command as a privileged user and reboot when ready to switch to
the updated BE:

beadm activate {be_name_clone}
""").format(**self.__dict__))

                def activate_be():
                        # Delete the snapshot that was taken before we
                        # updated the image and the boot archive.
                        logger.info(_("{0} has been updated "
                            "successfully").format(self.be_name))

                        os.rmdir(self.clone_dir)
                        self.destroy_snapshot()
                        self.img.history.operation_snapshot = None

                self._store_image_state()

                # Ensure cache is flushed before activating and unmounting BE.
                self.img.cleanup_cached_content(progtrack=self.progress_tracker)

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
                except Exception as e:
                        caught_exception = e
                        if relock:
                                # Re-lock be image.
                                relock = False
                                self.img.lock()

                self._reset_image_state(failure=caught_exception)
                if relock:
                        # Activation was successful so the be image was
                        # unmounted and the parent image must be re-locked.
                        self.img.lock()

                if caught_exception:
                        self.img.history.log_operation_error(error=e)
                        raise caught_exception

        def restore_image(self):
                """Restore a failed update attempt."""

                # flush() is necessary here so that the warnings get printed
                # on a new line.
                if self.progress_tracker:
                        self.progress_tracker.flush()

                self._reset_image_state(failure=True)

                # Leave the clone around for debugging purposes if we're
                # operating on the live BE.
                if self.is_live_BE:
                        logger.error(_("The running system has not been "
                            "modified. Modifications were only made to a clone "
                            "of the running system.  This clone is mounted at "
                            "{0} should you wish to inspect it.").format(
                            self.clone_dir))

                else:
                        # Rollback and destroy the snapshot.
                        try:
                                if be.beRollback(self.be_name,
                                    self.snapshot_name) != 0:
                                        logger.error(_("pkg: unable to "
                                            "rollback BE {0} and restore "
                                            "image").format(self.be_name))

                                self.destroy_snapshot()
                                os.rmdir(self.clone_dir)
                        except Exception as e:
                                self.img.history.log_operation_error(error=e)
                                raise e

                        logger.error(_("{bename} failed to be updated. No "
                            "changes have been made to {bename}.").format(
                            bename=self.be_name))

        def destroy_snapshot(self):

                """Destroy a snapshot of the BE being operated on.
                Note that this will destroy the last created
                snapshot and does not support destroying
                multiple snapshots. Create another instance of
                BootEnv to manage multiple snapshots."""

                if be.beDestroySnapshot(self.be_name, self.snapshot_name) != 0:
                        logger.error(_("pkg: unable to destroy snapshot "
                            "{0}").format(self.snapshot_name))

        def restore_install_uninstall(self):

                """Restore a failed install or uninstall attempt.
                Clone the snapshot, mount the BE and
                notify user of its existence. Rollback
                if not operating on a live BE"""

                # flush() is necessary here so that the warnings get printed
                # on a new line.
                if self.progress_tracker:
                        self.progress_tracker.flush()

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
                                            "BE {0}").format(
                                            self.be_name_clone))
                                        return

                        if be.beMount(self.be_name_clone, self.clone_dir) != 0:
                                logger.error(_("pkg: unable to mount BE "
                                    "{name} on {clone_dir}").format(
                                    name=self.be_name_clone,
                                    clone_dir=self.clone_dir))
                                return

                        logger.error(_("The Boot Environment {name} failed "
                            "to be updated. A snapshot was taken before the "
                            "failed attempt and is mounted here {clone_dir}. "
                            "Use 'beadm unmount {clone_name}' and then "
                            "'beadm activate {clone_name}' if you wish to "
                            "boot to this BE.").format(name=self.be_name,
                            clone_dir=self.clone_dir,
                            clone_name=self.be_name_clone))
                else:
                        if be.beRollback(self.be_name, self.snapshot_name) != 0:
                                logger.error("pkg: unable to rollback BE "
                                    "{0}".format(self.be_name))

                        self.destroy_snapshot()

                        logger.error(_("The Boot Environment {bename} failed "
                            "to be updated. A snapshot was taken before the "
                            "failed attempt and has been restored so no "
                            "changes have been made to {bename}.").format(
                            bename=self.be_name))


class BootEnvNull(object):

        """BootEnvNull is a class that gets used when libbe doesn't exist."""

        def __init__(self, img, progress_tracker=None):
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
        def copy_be(src_be_name, dst_be_name):
                pass

        @staticmethod
        def rename_be(orig_name, new_name):
                pass

        @staticmethod
        def destroy_be(be_name):
                pass

        @staticmethod
        def cleanup_be(be_name):
                pass

        @staticmethod
        def mount_be(be_name, mntpt, include_bpool=False):
                return None

        @staticmethod
        def unmount_be(be_name, force=False):
                return None

        @staticmethod
        def set_default_be(be_name):
                pass

        @staticmethod
        def check_be_name(be_name):
                if be_name:
                        raise api_errors.BENamingNotSupported(be_name)

        @staticmethod
        def get_be_list():
                return []

        @staticmethod
        def get_be_names():
                return []

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

if "bemgmt" in locals():
        BootEnv = BeadmV2BootEnv
elif "be" in locals():
        BootEnv = BeadmV1BootEnv
else:
        BootEnv = BootEnvNull
