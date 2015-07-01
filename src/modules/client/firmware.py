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
# Copyright (c) 2013, 2015, Oracle and/or its affiliates. All rights reserved.
#
import os.path
import six
import sys

import pkg.misc as misc
import pkg.pkgsubprocess as subprocess
import pkg.portable as portable

from pkg.client.debugvalues import DebugValues
from pkg.actions.generic import quote_attr_value


class Firmware(object):
        def __init__(self):
            self.__firmware = {} # cache of things we've checked already

        def check_firmware(self, dep_action, firmware_name):
                """Check firmware dependency.
                returns ((true, false, none (internal error)),
                error text)"""

                firmware_dir = "/usr/lib/fwenum"
                # leverage smf test infrastructure
                cmds_dir = DebugValues["smf_cmds_dir"]
                if DebugValues["firmware-dependency-bypass"]:
                        return (True, None)
                if cmds_dir: # we're testing;
                        firmware_dir = cmds_dir

                args = [os.path.join(firmware_dir, firmware_name[len("feature/firmware/"):])]
                args.extend([
                    "{0}={1}".format(k, quote_attr_value(v))
                    for k,v in sorted(six.iteritems(dep_action.attrs))
                    if k not in ["type", "root-image", "fmri"]
                ])

                key = str(args)

                # use a cache since each check may be expensive and each
                # pkg version may have the same dependency.
                # ignore non-solaris systems here

                if portable.osname != "sunos" and key not in self.firmware:
                    self.__firmware[key] = (True, None)

                if key not in self.__firmware:
                        try:
                                proc = subprocess.Popen(args, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT)
                                buf = proc.stdout.readlines()
                                ret = proc.wait()
                                # if there was output, something went wrong.
                                # Since generic errors are often exit(1),
                                # map this to an internal error.
                                if ret == 1 and len(buf) > 0:
                                        ret = 255
                                if ret == 0:
                                        ans = (True, None)
                                elif 0 < ret <= 239:
                                        ans = (False, (_("There are {0} instances"
                                            " of downrev firmware for the '{1}' "
                                            " devices present on this system. "
                                            "Update each to version {2} or better."
                                            ).format(ret, args[1],
                                            dep_action.attrs.get("minimum-version",
                                            _("UNSPECIFIED")))))
                                elif ret == 240:
                                        ans = (False, (_("There are 240 or more "
                                            "instances of downrev firmware for the"
                                            "'{0}' devices present on this system. "
                                            "Update each to version {1} or better."
                                            ).format(args[1],
                                            dep_action.attrs.get("minimum-version",
                                            _("UNSPECIFIED")))))
                                elif ret < 0:
                                        ans = (None,
                                            (_("Firmware dependency error: {0} "
                                            " exited due to signal {1}").format(
                                            " ".join(args), misc.signame(-ret))))
                                else:
                                        ans = (None,
                                            (_("Firmware dependency error: General "
                                            "internal error {0} running '{1}': '{2}'"
                                            ).format(str(ret), " ".join(args),
                                            "\n".join(buf))))

                        except OSError as e:
                                # we have no enumerator installed.  This can
                                # occur if this driver is being installed
                                # for the first time or, more likely, we
                                # just added enumerators & a firmware dependency
                                # for the first time.  For now, drive on and
                                # ignore this to permit the addition of such
                                # dependencies concurrently with their
                                # enumerarators.
                                # ans = (None, (_("Firmware dependency error:"
                                # " Cannot exec {0}: {1}").format(" ".join(args)
                                # , str(e))))
                                ans = (True, 0)

                        self.__firmware[key] = ans

                return self.__firmware[key]
