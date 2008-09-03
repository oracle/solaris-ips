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

# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import subprocess
import sys
import os
import tempfile

from pkg.misc import msg, emsg

# Since pkg(1) may be installed without libbe installed
# check for libbe and import it if it exists.

try:
        import libbe as be
except ImportError:
        # All recovery actions are disabled when libbe can't be imported. 
        pass        

class BootEnv(object):

        """A BootEnv object is an object containing the logic for
        managing the recovery of image-update, install and uninstall
        operations.

        Recovery is only enabled for ZFS filesystems. Any operation
        attempted on UFS will not be handled by BootEnv.
        
        This class makes use of usr/lib/python*/vendor-packages/libbe.so
        as the python wrapper for interfacing with usr/lib/libbe. Both
        libraries are delivered by the SUNWinstall-libs package. This
        package is not required for pkg(1) to operate successfully. It is
        soft required, meaning if it exists the bootenv class will attempt
        to provide recovery support."""

        def __init__(self, root):
                self.be_name = None
                self.dataset = None
                self.be_name_clone = None
                self.clone_dir = None
                self.is_live_BE = False
                self.snapshot_name = None
                self.root = root
                rc = 0

                assert root != None

                # Check for the old beList() API since pkg(1) can be
                # back published and live on a system without the latest libbe.
                beVals = be.beList()
                if isinstance(beVals[0], int):
                        rc, self.beList = beVals
                else:
                        self.beList = beVals

                # Happens e.g. in zones (at least, for now)
                if not self.beList or rc != 0:
                        raise RuntimeError, "nobootenvironments"

                # Need to find the name of the BE we're operating on in order
                # to create a snapshot and/or a clone of the BE.

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
                        if root == '/':
                                if not beVals.get("active"):
                                        continue
                                else:
                                        self.is_live_BE = True
                        else:
                                if beVals.get("mountpoint") != root:
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
                        else:
                                emsg(_("pkg: unable to create an auto "
                                    "snapshot. pkg recovery is disabled."))
                                raise RuntimeError, "recoveryDisabled"
                        break
                        
                else:
                        # We will get here if we don't find find any BE's. e.g
                        # if were are on UFS.
                        raise RuntimeError, "recoveryDisabled"
                               
        def init_image_recovery(self, img):

                """Initialize for an image-update.
                        If we're operating on a live BE then clone the
                        live BE and operate on the clone.
                        If we're operating on a non-live BE we use
                        the already created snapshot"""
                
                if self.is_live_BE:

                        # Create a clone of the live BE and mount it.
                        self.destroy_snapshot()
                        
                        # Do nothing with the returned snapshot name
                        # that is taken of the clone during beCopy.
                        ret, self.be_name_clone, not_used = be.beCopy()
                        if ret != 0:
                                emsg(_("pkg: unable to create BE %s") % \
                                    self.be_name_clone)
                                return

                        if be.beMount(self.be_name_clone, self.clone_dir) != 0:
                                 emsg(_("pkg: attempt to mount %s failed.") % \
                                    self.be_name_clone)
                                 return

                        # Set the image to our new mounted BE. 
                        img.find_root(self.clone_dir)

        def activate_image(self):

                """Activate a clone of the BE being operated on.
                        If were operating on a non-live BE then
                        destroy the snapshot."""

                cmd = [ "/sbin/bootadm", "update-archive", "-R" ]
                ret = 0
     
                if self.is_live_BE:

                        cmd += [self.clone_dir]
                        # Activate the clone.
                        try:
                                ret = subprocess.call(cmd,
                                    stdout = file("/dev/null"),
                                    stderr = subprocess.STDOUT)
                        except OSError, e:
                                 emsg(_("pkg: A system error %s was caught "
                                    "executing %s") % (e, " ".join(cmd)))

                        if ret != 0:
                                emsg(_("pkg: '%s' failed. \nwith a return code "
                                    "of %d.") % (" ".join(cmd), ret))
                                return

                        if be.beActivate(self.be_name_clone) != 0:
                                emsg(_("pkg: unable to activate %s") \
                                    % self.be_name_clone)
                                return

                        if be.beUnmount(self.be_name_clone) != 0:
                                emsg(_("pkg: unable to unmount %s") \
                                    % self.clone_dir)
                                return
                                    
                        os.rmdir(self.clone_dir)
                        
                        msg(_("A clone of %s exists and has been "
                            "updated and activated. On next boot "
                            "the Boot Environment %s will be mounted "
                            "on '/'. Reboot when ready to switch to "
                            "this updated BE.") % \
                            (self.be_name, self.be_name_clone))

                else:                        
                        # Delete the snapshot that was taken before we
                        # updated the image and update the the boot archive.

                        cmd += [self.root]
                        try:
                                ret = subprocess.call(cmd, \
                                    stdout = file("/dev/null"), \
                                    stderr = subprocess.STDOUT)
                        except OSError, e:
                                emsg(_("pkg: The system error %s was caught "
                                    "executing %s") % (e, " ".join(cmd)))

                        if ret != 0:
                                emsg(_("pkg: '%s' failed \nwith a return code "
                                    "of %d.") % (" ".join(cmd), ret))
                                return
                                
                        msg(_("%s has been updated successfully") % \
                                (self.be_name))
                                
                        os.rmdir(self.clone_dir)
                        self.destroy_snapshot()
                
        def restore_image(self):

                """Restore a failed image-update attempt."""

                # Leave the clone around for debugging purposes if we're
                # operating on the live BE.
                if self.is_live_BE:
                        emsg(_(" The running system has not been modified. "
                            "Modifications were only made to a clone of the "
                            "running system.  This clone is mounted at %s "
                            "should you wish to inspect it.") % self.clone_dir)

                else:
                        # Rollback and destroy the snapshot.
                        if be.beRollback(self.be_name, self.snapshot_name) != 0:
                                emsg(_("pkg: unable to rollback BE %s and "
                                    "restore image") % self.be_name)

                        self.destroy_snapshot()
                        os.rmdir(self.clone_dir)

                        msg(_("%s failed to be updated. No changes have been "
                            "made to %s.") % (self.be_name, self.be_name))

        def destroy_snapshot(self):

                """Destroy a snapshot of the BE being operated on.
                        Note that this will destroy the last created
                        snapshot and does not support destroying
                        multiple snapshots. Create another instance of
                        BootEnv to manage multiple snapshots."""

                if be.beDestroySnapshot(self.be_name, self.snapshot_name) != 0:
                        emsg(_("pkg: unable to destroy snapshot %s") % \
                            self.snapshot_name)

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
                                        emsg(_("pkg: unable to create BE %s") \
                                           % self.be_name_clone)
                                        return

                        if be.beMount(self.be_name_clone, self.clone_dir) != 0:
                                emsg(_("pkg: unable to mount BE %s on %s") % \
                                    (self.be_name_clone, self.clone_dir))
                                return
                                
                        emsg(_("The Boot Environment %s failed to be updated. "
                            "A snapshot was taken before the failed attempt "
                            "and is mounted here %s. Use 'beadm unmount %s' "
                            "and then 'beadm activate %s' if you wish to boot "
                            "to this BE.") % (self.be_name, self.clone_dir,
                            self.be_name_clone, self.be_name_clone))
                else:
                        if be.beRollback(self.be_name, self.snapshot_name) != 0:
                                 emsg("pkg: unable to rollback BE %s" % \
                                    self.be_name)
                                    
                        self.destroy_snapshot()

                        emsg(_("The Boot Environment %s failed to be updated. "
                          "A snapshot was taken before the failed attempt "
                          "and has been restored so no changes have been "
                          "made to %s.") % (self.be_name, self.be_name))
                        


        def activate_install_uninstall(self):
                """Activate an install/uninstall attempt. Which just means
                        destroy the snapshot for the live and non-live case."""

                self.destroy_snapshot()
                
class BootEnvNull(object):

        """BootEnvNull is a class that gets used when libbe doesn't exist."""

        def __init__(self, root):
                pass

        def init_image_recovery(self, img):
                pass

        def activate_image(self):
                pass
                
        def restore_image(self):
                pass

        def destroy_snapshot(self):
                pass
                
        def restore_install_uninstall(self):
                pass

        def activate_install_uninstall(self):
                pass

if "be" not in locals():
        BootEnv = BootEnvNull

if __name__ == "__main__":
        pass
