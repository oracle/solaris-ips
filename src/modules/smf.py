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
# Copyright (c) 2011, Oracle and/or its affiliates. All rights reserved.
#

# This module provides a basic interface to smf.

import os

import pkg.pkgsubprocess as subprocess

from pkg.client import global_settings
from pkg.client.debugvalues import DebugValues

logger = global_settings.logger

# range of possible SMF service states
SMF_SVC_UNKNOWN      = 0
SMF_SVC_DISABLED     = 1
SMF_SVC_MAINTENANCE  = 2
SMF_SVC_TMP_DISABLED = 3
SMF_SVC_TMP_ENABLED  = 4
SMF_SVC_ENABLED      = 5

svcprop_path = "/usr/bin/svcprop"
svcadm_path  = "/usr/sbin/svcadm"
svcs_path = "/usr/bin/svcs"

class NonzeroExitException(Exception):
        def __init__(self, cmd, return_code, output):
                self.cmd = cmd
                self.return_code = return_code
                self.output = output

        def __unicode__(self):
                # To workaround python issues 6108 and 2517, this provides a
                # a standard wrapper for this class' exceptions so that they
                # have a chance of being stringified correctly.
                return str(self)

        def __str__(self):
                return "Cmd %s exited with status %d, and output '%s'" %\
                    (self.cmd, self.return_code, self.output)


def __call(args):
        # a way to invoke a separate executable for testing
        cmds_dir = DebugValues.get_value("smf_cmds_dir")
        if cmds_dir:
                args = (
                    os.path.join(cmds_dir,
                    args[0].lstrip("/")),) + args[1:]
        try:
                proc = subprocess.Popen(args, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT)
                buf = proc.stdout.readlines()
                ret = proc.wait()
        except OSError, e:
                raise RuntimeError, "cannot execute %s: %s" % (args, e)

        if ret != 0:
                raise NonzeroExitException(args, ret, buf)
        return buf

def get_state(fmri):
        """ return state of smf service """

        props = get_props(fmri)
        if not props:
                return SMF_SVC_UNKNOWN

        if "maintenance" in props.get("restarter/state", []):
                return SMF_SVC_MAINTENANCE

        status = props.get("general_ovr/enabled", None)
        if status is not None:
                if "true" in status:
                        return SMF_SVC_TMP_ENABLED
                return SMF_SVC_TMP_DISABLED
        status = props.get("general/enabled", None)
        if status is not None and "true" in status:
                return SMF_SVC_ENABLED
        return SMF_SVC_DISABLED

def is_disabled(fmri):
        return get_state(fmri) < SMF_SVC_TMP_ENABLED

def check_fmris(attr, fmris):
        """ Walk a set of fmris checking that each is fully specifed with
        an instance.
        If an FMRI is not fully specified and does not contain at least
        one special match character from fnmatch(5) the fmri is dropped
        from the set that is returned and an error message is logged.
        """

        if isinstance(fmris, basestring):
                fmris = set([fmris])
        chars = "*?[!^"
        for fmri in fmris.copy():
                is_glob = False
                for c in chars:
                        if c in fmri:
                                is_glob = True

                tmp_fmri = fmri
                if fmri.startswith("svc:"):
                        tmp_fmri = fmri.replace("svc:", "", 1)

                # check to see if we've got an instance already
                if ":" in tmp_fmri and not is_glob:
                        continue

                fmris.remove(fmri)
                if is_glob:
                        cmd = (svcs_path, "-H", "-o", "fmri", "%s" % fmri)
                        try:
                                instances = __call(cmd)
                                for instance in instances:
                                        fmris.add(instance.rstrip())
                        except NonzeroExitException:
                                continue # non-zero exit == not installed

                else:
                        logger.error(_("FMRI pattern might implicitly match " \
                            "more than one service instance."))
                        logger.error(_("Actuators for %(attr)s will not be run " \
                            "for %(fmri)s.") % locals())
        return fmris

def get_props(svcfmri):
        args = (svcprop_path, "-c", svcfmri)

        try:
                buf = __call(args)
        except NonzeroExitException:
                return {} # empty output == not installed

        return dict([
            l.strip().split(None, 1)
            for l in buf
        ])

def get_prop(fmri, prop):
        args = (svcprop_path, "-c", "-p", prop, fmri)
        buf = __call(args)
        assert len(buf) == 1, "Was expecting one entry, got:%s" % buf
        buf = buf[0].rstrip("\n")
        return buf

def enable(fmris, temporary=False):
        if not fmris:
                return
        if isinstance(fmris, basestring):
                fmris = (fmris,)
        args = [svcadm_path, "enable"]
        if temporary:
                args.append("-t")
        __call(tuple(args) + fmris)

def disable(fmris, temporary=False):
        if not fmris:
                return
        if isinstance(fmris, basestring):
                fmris = (fmris,)
        args = [svcadm_path, "disable", "-s"]
        if temporary:
                args.append("-t")
        __call(tuple(args) + fmris)

def mark(state, fmris):
        if not fmris:
                return
        if isinstance(fmris, basestring):
                fmris = (fmris,)
        __call((svcadm_path, "mark", state) + tuple(fmris))

def refresh(fmris):
        if not fmris:
                return
        if isinstance(fmris, basestring):
                fmris = (fmris,)
        __call((svcadm_path, "refresh") + tuple(fmris))

def restart(fmris):
        if not fmris:
                return
        if isinstance(fmris, basestring):
                fmris = (fmris,)
        __call((svcadm_path, "restart") + tuple(fmris))
