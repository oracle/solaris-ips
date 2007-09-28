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
        key_attr = "name"

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

        def install(self, image, orig):
                n2m = os.path.normpath(os.path.sep.join(
                    (image.get_root(), "etc/name_to_major")))

                # Check to see if the driver has already been installed.
                major = [
                    line.rstrip()
                    for line in file(n2m)
                    if line.split()[0] == self.attrs["name"]
                ]

                # In the case where the the packaging system thinks the driver
                # is installed and the driver database doesn't or vice versa,
                # complain.
                if (major and not orig) or (orig and not major):
                        print "packaging system and driver database disagree", \
                            "on whether '%s' is installed" % self.attrs["name"]

                if orig:
                        return self.update_install(image, orig)

                args = ( self.add_drv, "-n", "-b", image.get_root() )

                if "alias" in self.attrs:
                        args += (
                            "-i",
                            " ".join([ '"%s"' % x for x in self.attrlist("alias") ])
                        )
                if "class" in self.attrs:
                        for eachclass in self.attrlist("class"):
                                args += ( "-c", eachclass )
                if "perms" in self.attrs:
                        args += (
                            "-m",
                            ",".join(self.attrlist("perms"))
                        )
                if "policy" in self.attrs:
                        args += ( "-p", self.attrs["policy"] )
                if "privs" in self.attrs:
                        args += (
                            "-P",
                            ",".join(self.attrlist("privs"))
                        )

                args += ( self.attrs["name"], )

                retcode = subprocess.call(args)
                if retcode != 0:

                        print "%s (%s) install failed with return code %s" % \
                            (self.name, self.attrs["name"], retcode)
                        print "command run was ", args

        def update_install(self, image, orig):
                add_args = ( self.update_drv, "-b", image.get_root(), "-a" )
                rem_args = ( self.update_drv, "-b", image.get_root(), "-d" )

                nalias = self.attrs.get("alias", [])
                oalias = orig.attrs.get("alias", [])
                # If there's only one alias, we'll get a string back unenclosed
                # in a list, so we need enlist it.
                if isinstance(nalias, str):
                        nalias = [ nalias ]
                if isinstance(oalias, str):
                        oalias = [ oalias ]
                add_alias = set(nalias) - set(oalias)
                rem_alias = set(oalias) - set(nalias)

                if add_alias:
                        add_args += (
                            "-i",
                            " ".join([ '"%s"' % x for x in add_alias ])
                        )
                if rem_alias:
                        rem_args += (
                            "-i",
                            " ".join([ '"%s"' % x for x in rem_alias ])
                        )

                nperms = self.attrs.get("perms", [])
                operms = orig.attrs.get("perms", [])
                if isinstance(nperms, str):
                        nperms = [ nperms ]
                if isinstance(operms, str):
                        operms = [ operms ]
                add_perms = set(nperms) - set(operms)
                rem_perms = set(operms) - set(nperms)

                if add_perms:
                        add_args += ( "-m", ",".join(add_perms) )
                if rem_perms:
                        rem_args += ( "-m", ",".join(rem_perms) )

                nprivs = self.attrs.get("privs", [])
                oprivs = orig.attrs.get("privs", [])
                if isinstance(nprivs, str):
                        nprivs = [ nprivs ]
                if isinstance(oprivs, str):
                        oprivs = [ oprivs ]
                add_privs = set(nprivs) - set(oprivs)
                rem_privs = set(oprivs) - set(nprivs)

                if add_privs:
                        add_args += ( "-P", ",".join(add_privs) )
                if rem_perms:
                        rem_args += ( "-P", ",".join(rem_privs) )

                npolicy = self.attrs.get("policy", "")
                opolicy = orig.attrs.get("policy", "")
                if npolicy:
                        add_args += ( "-p", npolicy )
                if opolicy:
                        rem_args += ( "-p", opolicy )

                add_args += (self.attrs["name"], )
                rem_args += (self.attrs["name"], )

                if len(add_args) > 5:
                        retcode = subprocess.call(add_args)
                        if retcode != 0:
                                print "%s (%s) upgrade (add) failed with " \
                                    "return code %s" % \
                                    (self.name, self.attrs["name"], retcode)

                if len(rem_args) > 5:
                        retcode = subprocess.call(rem_args)
                        if retcode != 0:
                                print "%s (%s) upgrade (remove) failed with " \
                                    "return code %s" % \
                                    (self.name, self.attrs["name"], retcode)

        def remove(self, image):
                args = (
                    self.rem_drv,
                    "-b",
                    image.get_root(),
                    self.attrs["name"]
                )

                retcode = subprocess.call(args)
                if retcode != 0:
                        print "%s (%s) removal failed with return code %s" % \
                            (self.name, self.attrs["name"], retcode)

        def generate_indices(self):
		ret = {}
		if "name" in self.attrs:
                        ret["driver_name"] = self.attrs["name"]
                if "alias" in self.attrs:
                        ret["driver_aliases"] = self.attrs["alias"]
                return ret

