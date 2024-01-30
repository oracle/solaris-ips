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
# Copyright (c) 2008, 2024, Oracle and/or its affiliates.
#

import pkg.smf as smf
import pkg.actions
import os

import pkg.misc

from pkg.client.debugvalues import DebugValues
from pkg.client.imagetypes import IMG_USER, IMG_ENTIRE


class Actuator(object):
    """Actuators are action attributes that cause side effects
    on live images when those actions are updated, installed
    or removed.  Since no side effects are caused when the
    affected image isn't the current root image, the OS may
    need to cause the equivalent effect during boot.
    This is Solaris specific for now. """

    # Each set of attributes listed below determines what attributes
    # will be scanned for a given type of operation.  These sets must
    # match the logic found in exec_pre_actuators() and
    # exec_post_actuators() below or planning output may be incorrect.
    __install_actuator_attrs = set([
        "release-note",     # conditionally include this file
                            # in release notes
        "refresh_fmri",     # refresh this service on any change
        "restart_fmri",     # restart this service on any change
    ])

    __update_actuator_attrs = set([
        "reboot-needed",    # have to reboot to update this file
        "release-note",     # conditionally include this file
                            # in release notes
        "refresh_fmri",     # refresh this service on any change
        "restart_fmri",     # restart this service on any change
        "suspend_fmri",     # suspend this service during update
    ])

    __removal_actuator_attrs = set([
        "reboot-needed",    # have to reboot to update this file
        "refresh_fmri",     # refresh this service on any change
        "restart_fmri",     # restart this service on any change
        "disable_fmri"      # disable this service prior to removal
    ])

    __state__desc = {
            "install": {
                "disable_fmri": set(),
                "reboot-needed": set(),
                "refresh_fmri": set(),
                "release-note": [(pkg.actions.generic.NSG, pkg.fmri.PkgFmri)],
                "restart_fmri": set(),
                "suspend_fmri": set(),
            },
            "removal": {
                "disable_fmri": set(),
                "reboot-needed": set(),
                "refresh_fmri": set(),
                "release-note": [(pkg.actions.generic.NSG, pkg.fmri.PkgFmri)],
                "restart_fmri": set(),
                "suspend_fmri": set(),
            },
            "update": {
                "disable_fmri": set(),
                "reboot-needed": set(),
                "refresh_fmri": set(),
                "release-note": [(pkg.actions.generic.NSG, pkg.fmri.PkgFmri)],
                "restart_fmri": set(),
                "suspend_fmri": set(),
            },
    }

    def __init__(self):
        self.install = {}
        self.removal = {}
        self.update =  {}
        self.suspend_fmris = None
        self.tmp_suspend_fmris = None
        self.do_nothing = True
        self.cmd_path = ""
        self.sync_timeout = 0
        self.act_timed_out = False
        self.zone = None

    @staticmethod
    def getstate(obj, je_state=None):
        """Returns the serialized state of this object in a format
        that that can be easily stored using JSON, pickle, etc."""
        return pkg.misc.json_encode(Actuator.__name__, obj.__dict__,
            Actuator.__state__desc, je_state=je_state)

    @staticmethod
    def setstate(obj, state, jd_state=None):
        """Update the state of this object using previously serialized
        state obtained via getstate()."""

        # get the name of the object we're dealing with
        name = type(obj).__name__

        # decode serialized state into python objects
        state = pkg.misc.json_decode(name, state,
            Actuator.__state__desc, jd_state=jd_state)

        # bulk update
        obj.__dict__.update(state)

    @staticmethod
    def fromstate(state, jd_state=None):
        """Allocate a new object using previously serialized state
        obtained via getstate()."""
        rv = Actuator()
        Actuator.setstate(rv, state, jd_state)
        return rv

    def set_timeout(self, timeout):
        """ Set actuator timeout.
        'timeout'       Actuator timeout in seconds. The following
                        special values are allowed:
                          0: don't use synchronous actuators
                         -1: no timeout, wait until finished
        """
        self.sync_timeout = timeout

    def set_zone(self, zname):
        """Specify if actuators are supposed to be run within a zone.
        If 'zname' is None, actuators are run in the global zone,
        otherwise actuators are run in the zone 'zname'. The caller has
        to make sure the zone exists and is running. If there are any
        issues with calling an actuator in the zone, it will be
        ignored."""

        self.zone = zname

    @property
    def timed_out(self):
        return self.act_timed_out

    # Defining "boolness" of a class, Python 2 uses the special method
    # called __nonzero__() while Python 3 uses __bool__(). For Python
    # 2 and 3 compatibility, define __bool__() only, and let
    # __nonzero__ = __bool__
    def __bool__(self):
        return bool(self.install) or bool(self.removal) or \
            bool(self.update)

    __nonzero__ = __bool__

    # scan_* functions take ActionPlan arguments (see imageplan.py)
    def scan_install(self, ap):
        self.__scan(self.install, ap.dst, ap.p.destination_fmri,
            self.__install_actuator_attrs)

    def scan_removal(self, ap):
        self.__scan(self.removal, ap.src, ap.p.origin_fmri,
            self.__removal_actuator_attrs)

    def scan_update(self, ap):
        if ap.src:
            self.__scan(self.update, ap.src, ap.p.destination_fmri,
                self.__update_actuator_attrs)
        self.__scan(self.update, ap.dst, ap.p.destination_fmri,
            self.__update_actuator_attrs)

    def __scan(self, dictionary, act, fmri, actuator_attrs):
        attrs = act.attrs
        for a in set(attrs.keys()) & actuator_attrs:
            if a != "release-note":
                values = attrs[a]
                if not isinstance(values, list):
                    values = [values]
                dictionary.setdefault(a, set()).update(values)
            else:
                if act.name == "file": # ignore for non-files
                    dictionary.setdefault(a, list()).append(
                        (act, fmri))

    def get_list(self):
        """Returns a list of actuator value pairs, suitable for printing"""
        def check_val(dfmri):
            # For actuators which are a single, global function that
            # needs to get executed, simply print true.
            if hasattr(dfmri, "__call__") or isinstance(dfmri, list):
                return [ "true" ]
            else:
                return dfmri

        merge = {}
        for d in [self.removal, self.update, self.install]:
            for a in d.keys():
                for smf in check_val(d[a]):
                    merge.setdefault(a, set()).add(smf)

        if self.reboot_needed():
            merge["reboot-needed"] = set(["true"])
        else:
            merge["reboot-needed"] = set(["false"])
        return [(fmri, smf)
                for fmri in merge
                for smf in merge[fmri]
                ]

    def get_release_note_info(self):
        """Returns a list of tuples of possible release notes"""
        return self.update.get("release-note", []) + \
            self.install.get("release-note", [])

    def get_services_list(self):
        """Returns a list of services that would be restarted"""
        return [(fmri, smf) for fmri, smf in self.get_list()
            if smf not in ["true", "false"]]

    def __str__(self):
        return "\n".join("  {0:>16}: {1:}".format(fmri, smf)
                for fmri, smf in self.get_list())

    def reboot_advised(self):
        """Returns True if action install execution may require a
        reboot."""

        return bool("true" in self.install.get("reboot-needed", []))

    def reboot_needed(self):
        """Returns True if action execution requires a new boot
        environment."""

        return bool("true" in self.update.get("reboot-needed", [])) or \
            bool("true" in self.removal.get("reboot-needed", []))

    def __invoke(self, func, *args, **kwargs):
        """Execute SMF command. Remember if command timed out."""

        if self.zone:
            kwargs["zone"] = self.zone

        try:
            func(*args, **kwargs)
        except smf.NonzeroExitException as nze:
            if nze.return_code == smf.EXIT_TIMEOUT:
                self.act_timed_out = True
            elif " ".join(nze.output).startswith("zlogin:"):
                # Ignore zlogin errors; the worst which
                # can happen is that an actuator is not run
                # (disable is always run with -t).
                # Since we only test once if the zone is
                # runnning, this could happen if someone shuts
                # down the zone while we are in the process of
                # executing.
                pass
            else:
                raise

    def exec_prep(self, image):
        if not image.is_liveroot():
            # we're doing off-line pkg ops; we need
            # to support self-assembly milestone
            # so create the necessary marker file

            if image.type != IMG_USER:
                path = os.path.join(image.root,
                    ".SELF-ASSEMBLY-REQUIRED")
                # create only if it doesn't exist
                if not os.path.exists(path):
                    os.close(os.open(path,
                        os.O_EXCL  |
                        os.O_CREAT |
                        os.O_WRONLY))
            if not DebugValues["smf_cmds_dir"] and not self.zone:
                return

        self.do_nothing = False

    def exec_pre_actuators(self, image):
        """do pre execution actuator processing..."""

        if self.do_nothing:
            return

        suspend_fmris = self.update.get("suspend_fmri", set())
        tmp_suspend_fmris = set()

        disable_fmris = self.removal.get("disable_fmri", set())

        suspend_fmris = smf.check_fmris("suspend_fmri", suspend_fmris,
            zone=self.zone)
        disable_fmris = smf.check_fmris("disable_fmri", disable_fmris,
            zone=self.zone)
        # eliminate services not loaded or not running
        # remember those services enabled only temporarily

        for fmri in suspend_fmris.copy():
            state = smf.get_state(fmri, zone=self.zone)
            if state <= smf.SMF_SVC_TMP_ENABLED:
                suspend_fmris.remove(fmri)
            if state == smf.SMF_SVC_TMP_ENABLED:
                tmp_suspend_fmris.add(fmri)

        for fmri in disable_fmris.copy():
            if smf.is_disabled(fmri, zone=self.zone):
                disable_fmris.remove(fmri)

        self.suspend_fmris = suspend_fmris
        self.tmp_suspend_fmris = tmp_suspend_fmris

        params = tuple(suspend_fmris | tmp_suspend_fmris)

        if params:
            self.__invoke(smf.disable, params, temporary=True)

        params = tuple(disable_fmris)

        if params:
            self.__invoke(smf.disable, params)

    def exec_fail_actuators(self, image):
        """handle a failed install"""

        if self.do_nothing:
            return

        params = tuple(self.suspend_fmris |
            self.tmp_suspend_fmris)

        if params:
            self.__invoke(smf.mark, "maintenance", params)

    def exec_post_actuators(self, image):
        """do post execution actuator processing"""

        if self.do_nothing:
            return

        # handle callables first

        for act in self.removal.values():
            if hasattr(act, "__call__"):
                act()

        for act in self.install.values():
            if hasattr(act, "__call__"):
                act()

        for act in self.update.values():
            if hasattr(act, "__call__"):
                act()


        refresh_fmris = self.removal.get("refresh_fmri", set()) | \
            self.update.get("refresh_fmri", set()) | \
            self.install.get("refresh_fmri", set())

        restart_fmris = self.removal.get("restart_fmri", set()) | \
            self.update.get("restart_fmri", set()) | \
            self.install.get("restart_fmri", set())

        refresh_fmris = smf.check_fmris("refresh_fmri", refresh_fmris,
            zone=self.zone)
        restart_fmris = smf.check_fmris("restart_fmri", restart_fmris,
            zone=self.zone)

        # ignore services not present or not
        # enabled

        for fmri in refresh_fmris.copy():
            if smf.is_disabled(fmri, zone=self.zone):
                refresh_fmris.remove(fmri)

        params = tuple(refresh_fmris)

        if params:
            self.__invoke(smf.refresh, params, sync_timeout=self.sync_timeout)

        for fmri in restart_fmris.copy():
            if smf.is_disabled(fmri, zone=self.zone):
                restart_fmris.remove(fmri)

        params = tuple(restart_fmris)
        if params:
            self.__invoke(smf.restart, params, sync_timeout=self.sync_timeout)

        # reenable suspended services that were running
        # be sure to not enable services that weren't running
        # and temp. enable those services that were in that
        # state.

        params = tuple(self.suspend_fmris)
        if params:
            self.__invoke(smf.enable, params, sync_timeout=self.sync_timeout)

        params = tuple(self.tmp_suspend_fmris)
        if params:
            self.__invoke(smf.enable, params, temporary=True,
                sync_timeout=self.sync_timeout)
