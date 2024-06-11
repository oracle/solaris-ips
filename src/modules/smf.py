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
# Copyright (c) 2011, 2024, Oracle and/or its affiliates.
#

# This module provides a basic interface to smf.

import locale
import os
import shlex
import subprocess

import pkg.misc as misc

from pkg.client import global_settings
from pkg.client.debugvalues import DebugValues
from urllib.parse import urlparse

logger = global_settings.logger

# range of possible SMF service states
SMF_SVC_UNKNOWN      = 0
SMF_SVC_DISABLED     = 1
SMF_SVC_MAINTENANCE  = 2
SMF_SVC_TMP_DISABLED = 3
SMF_SVC_TMP_ENABLED  = 4
SMF_SVC_ENABLED      = 5

EXIT_OK              = 0
EXIT_FATAL           = 1
EXIT_INVALID_OPTION  = 2
EXIT_INSTANCE        = 3
EXIT_DEPENDENCY      = 4
EXIT_TIMEOUT         = 5

svcprop_path = "/usr/bin/svcprop"
svcadm_path  = "/usr/sbin/svcadm"
svccfg_path = "/usr/sbin/svccfg"
svcs_path = "/usr/bin/svcs"
zlogin_path = "/usr/sbin/zlogin"


class NonzeroExitException(Exception):
    def __init__(self, cmd, return_code, output):
        self.cmd = cmd
        self.return_code = return_code
        self.output = output

    def __str__(self):
        return "Cmd {0} exited with status {1:d}, and output '{2}'".format(
            self.cmd, self.return_code, self.output)


def __call(args, zone=None):
    # a way to invoke a separate executable for testing
    cmds_dir = DebugValues["smf_cmds_dir"]
    # returned values will be in the user's locale
    # so we need to ensure that the force_str uses
    # their locale.
    encoding = locale.getpreferredencoding(do_setlocale=False)
    if cmds_dir:
        args = (
            os.path.join(cmds_dir,
            args[0].lstrip("/")),) + args[1:]
    if zone:
        cmd = DebugValues["bin_zlogin"]
        if cmd is None:
            cmd = zlogin_path
        args = (cmd, zone) + args

    try:
        proc = subprocess.Popen(args, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT)
        buf = [misc.force_str(l, encoding=encoding)
               for l in proc.stdout.readlines()]
        ret = proc.wait()
    except OSError as e:
        raise RuntimeError("cannot execute {0}: {1}".format(args, e))

    if ret != 0:
        raise NonzeroExitException(args, ret, buf)
    return buf


def get_state(fmri, zone=None):
    """ return state of smf service """

    props = get_props(fmri, zone=zone)
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


def is_disabled(fmri, zone=None):
    return get_state(fmri, zone=zone) < SMF_SVC_TMP_ENABLED


def check_fmris(attr, fmris, zone=None):
    """ Walk a set of fmris checking that each is fully specified with
    an instance.
    If an FMRI is not fully specified and does not contain at least
    one special match character from fnmatch(7) the fmri is dropped
    from the set that is returned and an error message is logged.
    """

    if isinstance(fmris, str):
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
            cmd = (svcs_path, "-H", "-o", "fmri", "{0}".format(fmri))
            try:
                instances = __call(cmd, zone=zone)
                for instance in instances:
                    fmris.add(instance.rstrip())
            except NonzeroExitException:
                continue # non-zero exit == not installed

        else:
            logger.error(_("FMRI pattern might implicitly match " \
                "more than one service instance."))
            logger.error(_("Actuators for {attr} will not be run " \
                "for {fmri}.").format(**locals()))
    return fmris


def get_props(svcfmri, zone=None):
    args = (svcprop_path, "-c", svcfmri)

    try:
        buf = __call(args, zone=zone)
    except NonzeroExitException:
        return {} # empty output == not installed

    return dict([
        l.strip().split(None, 1)
        for l in buf
    ])


def set_prop(fmri, prop, value, zone=None):
    args = (svccfg_path, "-s", fmri, "setprop", "{0}={1}".format(prop,
        value))
    __call(args, zone=zone)


def get_prop(fmri, prop, zone=None):
    args = (svcprop_path, "-c", "-p", prop, fmri)
    buf = __call(args, zone=zone)
    assert len(buf) == 1, "Was expecting one entry, got:{0}".format(buf)
    string = buf[0].rstrip("\n")
    # String returned by svcprop is escaped for use in shell and needs
    # to be unescaped back to the original state.
    string = " ".join(shlex.split(string))
    return string


def enable(fmris, temporary=False, sync_timeout=0, zone=None):
    if not fmris:
        return
    if isinstance(fmris, str):
        fmris = (fmris,)

    args = [svcadm_path, "enable"]
    if sync_timeout:
        args.append("-s")
        if sync_timeout != -1:
            args.append("-T {0:d}".format(sync_timeout))
    if temporary:
        args.append("-t")
    # fmris could be a list so explicit cast is necessary
    __call(tuple(args) + tuple(fmris), zone=zone)


def disable(fmris, temporary=False, sync_timeout=0, zone=None):
    if not fmris:
        return
    if isinstance(fmris, str):
        fmris = (fmris,)
    args = [svcadm_path, "disable", "-s"]
    if sync_timeout > 0:
        args.append("-T {0:d}".format(sync_timeout))
    if temporary:
        args.append("-t")
    # fmris could be a list so explicit cast is necessary
    __call(tuple(args) + tuple(fmris), zone=zone)


def mark(state, fmris, zone=None):
    if not fmris:
        return
    if isinstance(fmris, str):
        fmris = (fmris,)
    args = [svcadm_path, "mark", state]
    # fmris could be a list so explicit cast is necessary
    __call(tuple(args) + tuple(fmris), zone=zone)


def refresh(fmris, sync_timeout=0, zone=None):
    if not fmris:
        return
    if isinstance(fmris, str):
        fmris = (fmris,)
    args = [svcadm_path, "refresh"]
    if sync_timeout:
        args.append("-s")
        if sync_timeout != -1:
            args.append("-T {0:d}".format(sync_timeout))
    # fmris could be a list so explicit cast is necessary
    __call(tuple(args) + tuple(fmris), zone=zone)


def restart(fmris, sync_timeout=0, zone=None):
    if not fmris:
        return
    if isinstance(fmris, str):
        fmris = (fmris,)
    args = [svcadm_path, "restart"]
    if sync_timeout:
        args.append("-s")
        if sync_timeout != -1:
            args.append("-T {0:d}".format(sync_timeout))
    # fmris could be a list so explicit cast is necessary
    __call(tuple(args) + tuple(fmris), zone=zone)


def clear(fmris, sync_timeout=0, zone=None):
    if not fmris:
        return
    if isinstance(fmris, str):
        fmris = (fmris,)
    args = [svcadm_path, "clear"]
    if sync_timeout:
        args.append("-s")
        if sync_timeout != -1:
            args.append("-T {0:d}".format(sync_timeout))
    # fmris could be a list so explicit cast is necessary
    __call(tuple(args) + tuple(fmris), zone=zone)
