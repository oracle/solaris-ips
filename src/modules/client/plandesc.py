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
# Copyright (c) 2012, Oracle and/or its affiliates. All rights reserved.
#

"""
PlanDescription and _ActionPlan classes

These classes are part of the public API, and any changes here may require
bumping CURRENT_API_VERSION in pkg.api

The PlanDescription class is a public interface which contains all the data
associated with an image-modifying operation.

The _ActionPlan class is a private interface used to keep track of actions
modified within an image during an image-modifying operation.
"""

import collections
import itertools
import operator
import simplejson as json

import pkg.actions
import pkg.client.actuator
import pkg.client.api_errors as apx
import pkg.client.linkedimage as li
import pkg.client.pkgplan
import pkg.client.pkgplan
import pkg.facet
import pkg.fmri
import pkg.misc
import pkg.version

from pkg.api_common import (PackageInfo, LicenseInfo)

UNEVALUATED       = 0 # nothing done yet
EVALUATED_PKGS    = 1 # established fmri changes
MERGED_OK         = 2 # created single merged plan
EVALUATED_OK      = 3 # ready to execute
PREEXECUTED_OK    = 4 # finished w/ preexecute
PREEXECUTED_ERROR = 5 # whoops
EXECUTED_OK       = 6 # finished execution
EXECUTED_ERROR    = 7 # failed

class _ActionPlan(collections.namedtuple("_ActionPlan", "p src dst")):
        """A named tuple used to keep track of all the actions that will be
        executed during an image-modifying procecure."""
        # Class has no __init__ method; pylint: disable=W0232
        # Use __slots__ on an old style class; pylint: disable=E1001

        __slots__ = []

        __state__desc = tuple([
            pkg.client.pkgplan.PkgPlan,
            pkg.actions.generic.NSG,
            pkg.actions.generic.NSG,
        ])

        @staticmethod
        def getstate(obj, je_state=None):
                """Returns the serialized state of this object in a format
                that that can be easily stored using JSON, pickle, etc."""
                return pkg.misc.json_encode(_ActionPlan.__name__, tuple(obj),
                    _ActionPlan.__state__desc, je_state=je_state)

        @staticmethod
        def fromstate(state, jd_state=None):
                """Allocate a new object using previously serialized state
                obtained via getstate()."""
                # Access to protected member; pylint: disable=W0212

                # get the name of the object we're dealing with
                name = _ActionPlan.__name__

                # decode serialized state into python objects
                state = pkg.misc.json_decode(name, state,
                    _ActionPlan.__state__desc, jd_state=jd_state)

                return _ActionPlan(*state)


class PlanDescription(object):
        """A class which describes the changes the plan will make."""

        __state__desc = {
            "_actuators": pkg.client.actuator.Actuator,
            "_cfg_mediators": {
                str: {
                    "version": pkg.version.Version,
                    "implementation-version": pkg.version.Version,
                }
            },
            "_changed_facets": pkg.facet.Facets,
            "_fmri_changes": [ ( pkg.fmri.PkgFmri, pkg.fmri.PkgFmri ) ],
            "_new_avoid_obs": ( set(), set() ),
            "_new_facets": pkg.facet.Facets,
            "_new_mediators": collections.defaultdict(set, {
                str: {
                    "version": pkg.version.Version,
                    "implementation-version": pkg.version.Version,
                }
            }),
            "_removed_facets": set(),
            "_rm_aliases": { str: set() },
            "added_groups": { str: pkg.fmri.PkgFmri },
            "added_users": { str: pkg.fmri.PkgFmri },
            "children_ignored": [ li.LinkedImageName ],
            "children_nop": [ li.LinkedImageName ],
            "children_planned": [ li.LinkedImageName ],
            "install_actions": [ _ActionPlan ],
            "li_ppkgs": frozenset([ pkg.fmri.PkgFmri ]),
            "li_props": { li.PROP_NAME: li.LinkedImageName },
            "pkg_plans": [ pkg.client.pkgplan.PkgPlan ],
            "release_notes": (bool, []),
            "removal_actions": [ _ActionPlan ],
            "removed_groups": { str: pkg.fmri.PkgFmri },
            "removed_users": { str: pkg.fmri.PkgFmri },
            "update_actions": [ _ActionPlan ],
        }

        __state__commonize = frozenset([
            pkg.actions.generic.NSG,
            pkg.client.pkgplan.PkgPlan,
            pkg.fmri.PkgFmri,
        ])

        def __init__(self, op=None):
                self.state = UNEVALUATED
                self._op = op

                #
                # Properties set when state >= EVALUATED_PKGS
                #
                self._image_lm = None
                self._cfg_mediators = {}
                self._varcets_change = False
                self._new_variants = None
                self._changed_facets = pkg.facet.Facets()
                self._removed_facets = set()
                self._new_facets = None
                self._new_mediators = collections.defaultdict(set)
                self._mediators_change = False
                self._new_avoid_obs = (set(), set())
                self._fmri_changes = [] # install  (None, fmri)
                                        # remove   (oldfmri, None)
                                        # update   (oldfmri, newfmri|oldfmri)
                self._solver_summary = []
                self._solver_errors = None
                self.li_attach = False
                self.li_ppkgs = frozenset()
                self.li_ppubs = None
                self.li_props = {}

                #
                # Properties set when state >= EVALUATED_OK
                #
                # raw actions
                self.pkg_plans = []
                # merged actions
                self.removal_actions = []
                self.update_actions = []
                self.install_actions = []
                # smf and other actuators (driver actions get added during
                # execution stage).
                self._actuators = pkg.client.actuator.Actuator()
                # Used to track users and groups that are part of operation.
                self.added_groups = {}
                self.added_users = {}
                self.removed_groups = {}
                self.removed_users = {}
                # release notes that are part of this operation
                self.release_notes = (False, [])
                # plan properties
                self._cbytes_added = 0 # size of compressed files
                self._bytes_added = 0  # size of files added
                self._need_boot_archive = None
                # child properties
                self.child_op = None
                self.child_kwargs = {}
                self.children_ignored = None
                self.children_planned = []
                self.children_nop = []
                # driver aliases to remove
                self._rm_aliases = {}

                #
                # Properties set when state >= EXECUTED_OK
                #
                self._salvaged = []
                self.release_notes_name = None

                #
                # Set by imageplan.set_be_options()
                #
                self._backup_be = None
                self._backup_be_name = None
                self._new_be = None
                self._be_name = None
                self._be_activate = False

                # Accessed via imageplan.update_index
                self._update_index = True

                # stats about the current image
                self._cbytes_avail = 0  # avail space for downloads
                self._bytes_avail = 0   # avail space for fs

        @staticmethod
        def getstate(obj, je_state=None, reset_volatiles=False):
                """Returns the serialized state of this object in a format
                that that can be easily stored using JSON, pickle, etc."""
                # Access to protected member; pylint: disable=W0212

                if reset_volatiles:
                        # backup and clear volatiles
                        _bytes_avail = obj._bytes_avail
                        _cbytes_avail = obj._cbytes_avail
                        obj._bytes_avail = obj._cbytes_avail = 0

                name = PlanDescription.__name__
                state = pkg.misc.json_encode(name, obj.__dict__,
                    PlanDescription.__state__desc,
                    commonize=PlanDescription.__state__commonize,
                    je_state=je_state)

                # add a state version encoding identifier
                state[name] = 0

                if reset_volatiles:
                        obj._bytes_avail = obj._bytes_avail
                        obj._cbytes_avail = obj._cbytes_avail

                return state

        @staticmethod
        def setstate(obj, state, jd_state=None):
                """Update the state of this object using previously serialized
                state obtained via getstate()."""
                # Access to protected member; pylint: disable=W0212

                # get the name of the object we're dealing with
                name = PlanDescription.__name__

                # version check and delete the encoding identifier
                assert state[name] == 0
                del state[name]

                # decode serialized state into python objects
                state = pkg.misc.json_decode(name, state,
                    PlanDescription.__state__desc,
                    commonize=PlanDescription.__state__commonize,
                    jd_state=jd_state)

                # bulk update
                obj.__dict__.update(state)

                # clear volatiles
                obj._cbytes_avail = 0
                obj._bytes_avail = 0

        @staticmethod
        def fromstate(state, jd_state=None):
                """Allocate a new object using previously serialized state
                obtained via getstate()."""
                rv = PlanDescription()
                PlanDescription.setstate(rv, state, jd_state)
                return rv

        def _save(self, fobj, reset_volatiles=False):
                """Save a json encoded representation of this plan
                description objects into the specified file object."""

                state = PlanDescription.getstate(self,
                    reset_volatiles=reset_volatiles)
                try:
                        fobj.truncate()
                        json.dump(state, fobj, encoding="utf-8")
                        fobj.flush()
                except OSError, e:
                        # Access to protected member; pylint: disable=W0212
                        raise apx._convert_error(e)

                del state

        def _load(self, fobj):
                """Load a json encoded representation of a plan description
                from the specified file object."""

                assert self.state == UNEVALUATED

                try:
                        fobj.seek(0)
                        state = json.load(fobj, encoding="utf-8")
                except OSError, e:
                        # Access to protected member; pylint: disable=W0212
                        raise apx._convert_error(e)

                PlanDescription.setstate(self, state)
                del state

        def _executed_ok(self):
                """A private interface used after a plan is successfully
                invoked to free up memory."""

                # reduce memory consumption
                self._fmri_changes = []
                self._actuators = pkg.client.actuator.Actuator()
                self.added_groups = {}
                self.added_users = {}
                self.removed_groups = {}
                self.removed_users = {}

        @property
        def executed(self):
                """A boolean indicating if we attempted to execute this
                plan."""
                return self.state in [EXECUTED_OK, EXECUTED_ERROR]

        @property
        def services(self):
                """Returns a list of string tuples describing affected services
                (action, SMF FMRI)."""
                return sorted(
                    ((str(a), str(smf_fmri))
                    for a, smf_fmri in self._actuators.get_services_list()),
                        key=operator.itemgetter(0, 1)
                )

        @property
        def mediators(self):
                """Returns a list of three-tuples containing information about
                the mediators.  The first element in the tuple is the name of
                the mediator.  The second element is a tuple containing the
                original version and source and the new version and source of
                the mediator.  The third element is a tuple containing the
                original implementation and source and new implementation and
                source."""

                ret = []

                if not self._mediators_change or \
                    (not self._cfg_mediators and not self._new_mediators):
                        return ret

                def get_mediation(mediators, m):
                        # Missing docstring; pylint: disable=C0111
                        mimpl = mver = mimpl_source = \
                            mver_source = None
                        if m in mediators:
                                mimpl = mediators[m].get(
                                    "implementation")
                                mimpl_ver = mediators[m].get(
                                    "implementation-version")
                                if mimpl_ver:
                                        mimpl_ver = \
                                            mimpl_ver.get_short_version()
                                if mimpl and mimpl_ver:
                                        mimpl += "(@%s)" % mimpl_ver
                                mimpl_source = mediators[m].get(
                                    "implementation-source")

                                mver = mediators[m].get("version")
                                if mver:
                                        mver = mver.get_short_version()
                                mver_source = mediators[m].get(
                                    "version-source")
                        return mimpl, mver, mimpl_source, mver_source

                for m in sorted(set(self._new_mediators.keys() +
                    self._cfg_mediators.keys())):
                        orig_impl, orig_ver, orig_impl_source, \
                            orig_ver_source = get_mediation(
                                self._cfg_mediators, m)
                        new_impl, new_ver, new_impl_source, new_ver_source = \
                            get_mediation(self._new_mediators, m)

                        if orig_ver == new_ver and \
                            orig_ver_source == new_ver_source and \
                            orig_impl == new_impl and \
                            orig_impl_source == new_impl_source:
                                # Mediation not changed.
                                continue

                        out = (m,
                            ((orig_ver, orig_ver_source),
                            (new_ver, new_ver_source)),
                            ((orig_impl, orig_impl_source),
                            (new_impl, new_impl_source)))

                        ret.append(out)

                return ret

        def get_mediators(self):
                """Returns list of strings describing mediator changes."""

                ret = []
                for m, ver, impl in sorted(self.mediators):
                        ((orig_ver, orig_ver_source),
                            (new_ver, new_ver_source)) = ver
                        ((orig_impl, orig_impl_source),
                            (new_impl, new_impl_source)) = impl
                        out = "mediator %s:\n" % m
                        if orig_ver and new_ver:
                                out += "           version: %s (%s default) " \
                                    "-> %s (%s default)\n" % (orig_ver,
                                    orig_ver_source, new_ver, new_ver_source)
                        elif orig_ver:
                                out += "           version: %s (%s default) " \
                                    "-> None\n" % (orig_ver, orig_ver_source)
                        elif new_ver:
                                out += "           version: None -> " \
                                    "%s (%s default)\n" % (new_ver,
                                    new_ver_source)

                        if orig_impl and new_impl:
                                out += "    implementation: %s (%s default) " \
                                    "-> %s (%s default)\n" % (orig_impl,
                                    orig_impl_source, new_impl, new_impl_source)
                        elif orig_impl:
                                out += "    implementation: %s (%s default) " \
                                    "-> None\n" % (orig_impl, orig_impl_source)
                        elif new_impl:
                                out += "    implementation: None -> " \
                                    "%s (%s default)\n" % (new_impl,
                                    new_impl_source)
                        ret.append(out)
                return ret

        @property
        def plan_desc(self):
                """Get the proposed fmri changes."""
                return self._fmri_changes

        @property
        def salvaged(self):
                """A list of tuples of items that were salvaged during plan
                execution.  Each tuple is of the form (original_path,
                salvage_path).  Where 'original_path' is the path of the item
                before it was salvaged, and 'salvage_path' is where the item was
                moved to.  This property is only valid after plan execution
                has completed."""
                assert self.executed
                return self._salvaged

        @property
        def varcets(self):
                """Returns a tuple of two lists containing the facet and variant
                changes in this plan."""
                vs = []
                if self._new_variants:
                        vs = self._new_variants.items()
                fs = []
                fs.extend(self._changed_facets.items())
                fs.extend([(f, None) for f in self._removed_facets])
                return (vs, fs)

        def get_varcets(self):
                """Returns a formatted list of strings representing the
                variant/facet changes in this plan"""
                vs, fs = self.varcets
                ret = []
                ret.extend(["variant %s: %s" % a for a in vs])
                ret.extend(["  facet %s: %s" % a for a in fs])
                return ret

        def get_changes(self):
                """A generation function that yields tuples of PackageInfo
                objects of the form (src_pi, dest_pi).

                If 'src_pi' is None, then 'dest_pi' is the package being
                installed.

                If 'src_pi' is not None, and 'dest_pi' is None, 'src_pi'
                is the package being removed.

                If 'src_pi' is not None, and 'dest_pi' is not None,
                then 'src_pi' is the original version of the package,
                and 'dest_pi' is the new version of the package it is
                being upgraded to."""

                for pp in sorted(self.pkg_plans,
                    key=operator.attrgetter("origin_fmri", "destination_fmri")):
                        yield (PackageInfo.build_from_fmri(pp.origin_fmri),
                            PackageInfo.build_from_fmri(pp.destination_fmri))

        def get_actions(self):
                """A generator function that yields action change descriptions
                in the order they will be performed."""

                # Unused variable '%s'; pylint: disable=W0612
                for pplan, o_act, d_act in itertools.chain(
                    self.removal_actions,
                    self.update_actions,
                    self.install_actions):
                # pylint: enable=W0612
                        yield "%s -> %s" % (o_act, d_act)

        def has_release_notes(self):
                """True if there are release notes for this plan"""
                return bool(self.release_notes[1])

        def must_display_notes(self):
                """True if the release notes must be displayed"""
                return self.release_notes[0]

        def get_release_notes(self):
                """A generator that returns the release notes for this plan"""
                for notes in self.release_notes[1]:
                        yield notes

        def get_licenses(self, pfmri=None):
                """A generator function that yields information about the
                licenses related to the current plan in tuples of the form
                (dest_fmri, src, dest, accepted, displayed) for the given
                package FMRI or all packages in the plan.  This is only
                available for licenses that are being installed or updated.

                'dest_fmri' is the FMRI of the package being installed.

                'src' is a LicenseInfo object if the license of the related
                package is being updated; otherwise it is None.

                'dest' is the LicenseInfo object for the license that is being
                installed.

                'accepted' is a boolean value indicating that the license has
                been marked as accepted for the current plan.

                'displayed' is a boolean value indicating that the license has
                been marked as displayed for the current plan."""

                for pp in self.pkg_plans:
                        dfmri = pp.destination_fmri
                        if pfmri and dfmri != pfmri:
                                continue

                        # Unused variable; pylint: disable=W0612
                        for lid, entry in pp.get_licenses():
                                src = entry["src"]
                                src_li = None
                                if src:
                                        src_li = LicenseInfo(pp.origin_fmri,
                                            src, img=pp.image)

                                dest = entry["dest"]
                                dest_li = None
                                if dest:
                                        dest_li = LicenseInfo(
                                            pp.destination_fmri, dest,
                                            img=pp.image)

                                yield (pp.destination_fmri, src_li, dest_li,
                                    entry["accepted"], entry["displayed"])

                        if pfmri:
                                break

        def get_solver_errors(self):
                """Returns a list of strings for all FMRIs evaluated by the
                solver explaining why they were rejected.  (All packages
                found in solver's trim database.)  Only available if
                DebugValues["plan"] was set when the plan was created.
                """

                assert self.state >= EVALUATED_PKGS, \
                        "%s >= %s" % (self.state, EVALUATED_PKGS)

                # in case this operation doesn't use solver
                if self._solver_errors is None:
                        return []

                return self._solver_errors

        @property
        def plan_type(self):
                """Return the type of plan that was created (ex:
                API_OP_UPDATE)."""
                return self._op

        @property
        def update_index(self):
                """Boolean indicating if indexes will be updated as part of an
                image-modifying operation."""
                return self._update_index

        @property
        def backup_be(self):
                """Either None, True, or False.  If None then executing this
                plan may create a backup BE.  If False, then executing this
                plan will not create a backup BE.  If True, then executing
                this plan will create a backup BE."""
                return self._backup_be

        @property
        def be_name(self):
                """The name of a new BE that will be created if this plan is
                executed."""
                return self._be_name

        @property
        def backup_be_name(self):
                """The name of a new backup BE that will be created if this
                plan is executed."""
                return self._backup_be_name

        @property
        def activate_be(self):
                """A boolean value indicating whether any new boot environment
                will be set active on next boot."""
                return self._be_activate

        @property
        def reboot_needed(self):
                """A boolean value indicating that execution of the plan will
                require a restart of the system to take effect if the target
                image is an existing boot environment."""
                return self._actuators.reboot_needed()

        @property
        def new_be(self):
                """A boolean value indicating that execution of the plan will
                take place in a clone of the current live environment"""
                return self._new_be

        @property
        def update_boot_archive(self):
                """A boolean value indicating whether or not the boot archive
                will be rebuilt"""
                return self._need_boot_archive

        @property
        def bytes_added(self):
                """Estimated number of bytes added"""
                return self._bytes_added

        @property
        def cbytes_added(self):
                """Estimated number of download cache bytes added"""
                return self._cbytes_added

        @property
        def bytes_avail(self):
                """Estimated number of bytes available in image /"""
                return self._bytes_avail

        @property
        def cbytes_avail(self):
                """Estimated number of bytes available in download cache"""
                return self._cbytes_avail
