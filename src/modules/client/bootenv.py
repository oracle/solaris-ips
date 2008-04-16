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

# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import subprocess
import sys
import os
import tempfile

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

                assert root != None

                self.beList = be.beList()

                # Happens e.g. in zones (at least, for now)
                if not self.beList:
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
                        #
                        # Another issue is that a BE could have a mountpoint
                        # property of "legacy". We only need to check when '/'
                        # is legacy since an alternate root with a mountpoint
                        # property of legacy won't be mounted. We accomplish
                        # this by checking that "active" == True and
                        # root == '/'.
                        
                        is_active = beVals.get("active")
                        be_name = beVals.get("orig_be_name")

                        if not be_name and not beVals.get("mounted"):
                                continue
                                
                        if beVals.get("mountpoint") != root and not is_active:
                                continue

                        if root == '/' and is_active:
                                self.is_live_BE = True

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
                                print >> sys.stderr, \
                                        _("pkg: unable to create an auto "
                                         "snapshot. pkg recovery is disabled.")
                                raise RuntimeError, "recoveryDisabled"

                        self.be_name_clone = self.be_name + "_" + \
                            self.snapshot_name
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
                        ret, self.be_name_clone, notUsed = be.beCopy()                        
                        if ret != 0:
                                print >> sys.stderr, \
                                    _("pkg: unable to create BE %s") % \
                                    self.be_name_clone

                        if be.beMount(self.be_name_clone, self.clone_dir) != 0:
                                print >> sys.stderr, \
                                    _("pkg: attempt to mount %s failed.") % \
                                    self.be_name

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
                                print >> sys.stderr, \
                                    _("pkg: A system error %s was caught "
                                    "executing %s") % (e, " ".join(cmd))

                        if ret != 0:
                                print >> sys.stderr, \
                                    _("pkg: '%s' failed. \nwith a return code "
                                    "of %d.") % (" ".join(cmd), ret)
                                return

                        if be.beActivate(self.be_name_clone) != 0:
                                print >> sys.stderr, \
                                    _("pkg: unable to activate %s") \
                                    % self.be_name_clone
                                return

                        if be.beUnmount(self.be_name_clone) != 0:
                                print >> sys.stderr, \
                                    _("pkg: unable to unmount %s") \
                                    % self.clone_dir
                                return
                                    
                        os.rmdir(self.clone_dir)
                        
                        print >> sys.stdout, \
                                _("A clone of %s exists and has been "
                                "updated and activated. On next boot "
                                "the Boot Environment %s will be mounted "
                                "on '/'. Reboot when ready to switch to "
                                "this updated BE.") % \
                                (self.be_name, self.be_name_clone)

                else:                        
                        # Delete the snapshot that was taken before we
                        # updated the image and update the the boot archive.

                        cmd += [self.root]
                        try:
                                ret = subprocess.call(cmd, \
                                    stdout = file("/dev/null"), \
                                    stderr = subprocess.STDOUT)
                        except OSError, e:
                                print >> sys.stderr, \
                                    _("pkg: The system error %s was caught "
                                    "executing %s") % (e, " ".join(cmd))

                        if ret != 0:
                                print >> sys.stderr, \
                                    _("pkg: '%s' failed \nwith a return code "
                                    "of %d.") % (" ".join(cmd), ret)
                                return
                                
                        print >> sys.stdout, \
                                _("%s has been updated successfully") % \
                                (self.be_name)
                                
                        os.rmdir(self.clone_dir)
                        self.destroy_snapshot()
                
        def restore_image(self):

                """Restore a failed image-update attempt."""

                # Leave the clone around for debugging purposes if we're
                # operating on the live BE.
                if self.is_live_BE:
                        print >> sys.stderr, \
                            _(" The running system has not been modified. "
                            "Modifications were only made to a clone of the "
                            "running system.  This clone is mounted at %s "
                            "should you wish to inspect it.") % self.clone_dir

                else:
                        # Rollback and destroy the snapshot.
                        if be.beRollback(self.be_name, self.snapshot_name) != 0:
                                print >> sys.stderr, \
                                    _("pkg: unable to rollback BE %s "
                                    "and restore image") % \
                                    self.be_name

                        self.destroy_snapshot()
                        os.rmdir(self.clone_dir)

                        print >> sys.stdout, \
                            _("%s failed to be updated. No changes have been "
                            "made to %s.") % (self.be_name, self.be_name)

        def destroy_snapshot(self):

                """Destroy a snapshot of the BE being operated on.
                        Note that this will destroy the last created
                        snapshot and does not support destroying
                        multiple snapshots. Create another instance of
                        BootEnv to manage multiple snapshots."""

                if be.beDestroySnapshot(self.be_name, self.snapshot_name) != 0:
                        print >> sys.stderr, \
                            _("pkg: unable to destroy snapshot %s") % \
                            self.snapshot_name

        def restore_install_uninstall(self):

                """Restore a failed install or uninstall attempt.
                        Clone the snapshot, mount the BE and
                        notify user of its existence. Rollback
                        if not operating on a live BE"""

                if self.is_live_BE:
                        # Create a new BE based on the previously taken
                        # snapshot. Note that we need to create our own name
                        # for the BE since be_copy can't create one based
                        # off of a snapshot name.

                        ret, notUsed, notUsed2 = \
                            be.beCopy(self.be_name_clone, self.be_name, \
                            self.snapshot_name)      
                        if ret != 0:
                                print >> sys.stderr, \
                                    _("pkg: unable to create BE %s") % \
                                    self.be_name_clone

                        if be.beMount(self.be_name_clone, self.clone_dir) != 0:
                                print >> sys.stderr, \
                                    _("pkg: unable to mount BE %s on %s") % \
                                    (self.be_name_clone, self.clone_dir)
                                
                        print >> sys.stderr, \
                            _("The Boot Environment %s failed to be updated. A "
                            "snapshot was taken before the failed attempt "
                            "and is mounted here %s. Use 'beadm activate %s "
                            "and reboot if you wish to boot to this BE.") % \
                            (self.be_name, self.clone_dir, self.be_name_clone)
        
                else:
                        if be.beRollback(self.be_name, self.snapshot_name) != 0:
                                print >> sys.stderr, \
                                   "pkg: unable to rollback BE %s" % \
                                    self.be_name
                                    
                        self.destroy_snapshot()

                        print >> sys.stderr, \
                          _("The Boot Environment %s failed to be updated. "
                          "A snapshot was taken before the failed attempt "
                          "and has been restored so no changes have been "
                          "made to %s.") % (self.be_name, self.be_name)
                        


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
