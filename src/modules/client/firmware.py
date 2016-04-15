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
# Copyright (c) 2013, 2016, Oracle and/or its affiliates. All rights reserved.
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
            self._cache = {}  # cache of things we've checked already

        def _check(self, dep_action, which):
                """Performs the subprocess invocation and returns
                (status, outputbuffer) to the caller"""

                # leverage smf test infrastructure
                cmds_dir = DebugValues["smf_cmds_dir"]
                if DebugValues["firmware-dependency-bypass"]:
                        return (True, None)
                if cmds_dir:  # we're testing;
                        firmware_dir = cmds_dir
                else:
                        firmware_dir = "/usr/lib/fwenum"

                args = [os.path.join(firmware_dir, which)]
                args.extend([
                        "{0}={1}".format(k, quote_attr_value(v))
                        for k, v in sorted(six.iteritems(dep_action.attrs))
                ])

                # Set up the default return values
                ret = 0
                buf = ""

                # use a cache since each check may be expensive and each
                # pkg version may have the same dependency.
                # ignore non-solaris systems here

                if portable.osname != "sunos" and key not in self._cache:
                        self._cache[key] = (True, None)

                if str(args) not in self._cache:
                        try:
                                proc = subprocess.Popen(
                                    args,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT)
                                # output from proc is bytes
                                buf = [misc.force_str(l) for l in
                                    proc.stdout.readlines()]
                                ret = proc.wait()

                        except OSError as e:
                                # we have no enumerator installed.  This can
                                # occur if this driver is being installed for
                                # the first time or, more likely, we just added
                                # enumerators and a firmware dependency for the
                                # first time. For now, drive on and ignore this
                                # to permit the addition of such dependencies
                                # concurrently with their enumerarators.
                                buf = (_("Firmware dependency error:"
                                         " Cannot exec {0}: {1}").format(
                                                 " ".join(args), str(e)))
                                ret = -1
                return (ret, buf, args)


class Cpu(Firmware):
        """Check cpu dependency.
        returns ((true, false, none (internal error)), error text)"""

        def check(self, dep_action, enumerator):
                (ret, buf, args) = self._check(dep_action, which="cpu")
                if ret == 0:
                        ans = (True, None)
                elif ret == -1:
                        ans = (True, 0)
                elif ret == 1:
                        # the cpu version enumerator returns 1 and
                        # prints the appropriate string if the system
                        # we're running this on does not match the
                        # required (include/exclude) condition.
                        # We're not checking for valid args here since
                        # since that's already been done by the enumerator
                        checkargs = dict([j.split("=") for j in
                                         args if j.startswith("check.")])
                        pvtype = checkargs["check.version-type"]
                        if pvtype == "iset":
                            vtype = "Instruction Set Element(s)"
                        elif pvtype == "plat":
                            vtype = "Platform Name(s)"
                        else:
                            vtype = "CPU Name(s)"
                        try:
                            innit = checkargs["check.include"] or None
                            mesg = "include: {0}".format(innit)
                        except KeyError as ke:
                            pass
                        try:
                            notit = checkargs["check.exclude"] or None
                            mesg = "exclude: {0}".format(notit)
                        except KeyError as ke:
                            pass

                        ans = (False,
                               (_("cpu dependency error: '{0}' does "
                                  "not meet the the minimum "
                                  "requirement for {1} {2}\n").
                                format("".join(buf).rstrip(),
                                       vtype, mesg)))
                else:
                        # enumerator error
                        ans = (False,
                               (_("cpu dependency error: "
                                  "Unable to verify cpu type\n")))
                key = str(args)
                self._cache[key] = ans
                return self._cache[key]


class Driver(Firmware):
        """Check driver firmware dependency.
        returns ((true, false, none (internal error)), error text)"""

        def check(self, dep_action, enumerator):
                which = enumerator[len("feature/firmware/"):]
                (ret, buf, args) = self._check(dep_action, which=which)
                # if there was output, something went wrong.

                min_ver = dep_action.attrs.get(
                    "check.minimum-version",
                    dep_action.attrs.get("minimum-version", _("UNSPECIFIED")))
                # Since generic errors are often exit(1),
                # map this to an internal error.
                if ret == 1 and len(buf) > 0:
                        ret = 255
                if ret == 0:
                        ans = (True, None)
                elif ret == -1:
                        ans = (True, 0)
                elif 0 < ret <= 239:
                        ans = (False,
                               (_("There are {0} instances of downrev "
                                  "firmware for the '{1}' devices present "
                                  "on this system. Update each to version "
                                  "{2} or newer.").
                                format(ret, ret, min_ver)))
                elif ret == 240:
                        ans = (False,
                               (_("There are 240 or more "
                                  "instances of downrev firmware for the"
                                  "'{0}' devices present on this system. "
                                  "Update each to version {1} or better.").
                                format(ret, min_ver)))
                elif ret < 0:
                        ans = (None,
                               (_("Firmware dependency error: {0} "
                                  "exited due to signal {1}").format(
                                          " ".join(buf), misc.signame(-ret))))
                else:
                        ans = (None,
                               (_("Firmware dependency error: General "
                                  "internal error {0} running '{1}': '{2}'").
                                format(str(ret),
                                       " ".join(buf),
                                       "\n".join(buf))))
                key = str(args)
                self._cache[key] = ans
                return self._cache[key]
