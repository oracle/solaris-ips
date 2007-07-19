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
# Copyright 2007 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

"""module describing a driver packaging object.

This module contains the DriverAction class, which represents a driver-type
packaging object.
"""

import os
import subprocess
import sys

import generic

class DriverAction(generic.Action):
        """Class representing a driver-type packaging object."""

        name = "driver"
        attributes = ("name", "alias", "class", "perms", "policy", "privs")

        # XXX This is a gross hack to let us test the action without having to
        # be root.
        if "USR_SBIN" in os.environ:
                usr_sbin = os.environ["USR_SBIN"]
                if not usr_sbin.endswith("/"):
                        usr_sbin += "/"
        else:
                usr_sbin = "/usr/sbin/"

        add_drv = usr_sbin + "add_drv"
        rem_drv = usr_sbin + "rem_drv"
        update_drv = usr_sbin + "update_drv"

        def __init__(self, data=None, **attrs):
                generic.Action.__init__(self, data, **attrs)

        def install(self, image):
                n2m = os.path.normpath(os.path.sep.join(
                    (image.get_root(), "etc/name_to_major")))

                # Check to see if the driver has already been installed.
                major = [
                    line.rstrip()
                    for line in file(n2m)
                    if line.split()[0] == self.attrs["name"]
                ]

                if major:
                        return update_install(self, image)

                args = ( self.add_drv, "-n", "-b", image.get_root() )
                if "alias" in self.attrs:
                        args += (
                            "-i",
                            " ".join([ '"%s"' % x for x in self.attrs["alias"] ])
                        )
                if "class" in self.attrs:
                        args += ( "-c", self.attrs["class"] )
                if "perms" in self.attrs:
                        args += (
                            "-m",
                            ",".join(self.attrs["perms"])
                        )
                if "policy" in self.attrs:
                        args += ( "-p", self.attrs["policy"] )
                if "privs" in self.attrs:
                        args += (
                            "-P",
                            ",".join(self.attrs["privs"])
                        )

                args += ( self.attrs["name"], )

                retcode = subprocess.call(args)
                if retcode != 0:
                        print "%s (%s) action failed with return code %s" % \
                            (self.name, self.attrs["name"], retcode)

        def update_install(self, image):
                # XXX This needs to run update_drv or something.
                pass

        def generate_indices(self):
                return {
                    "driver_name": self.attrs["name"],
                    "driver_aliases": self.attrs["alias"]
                }
