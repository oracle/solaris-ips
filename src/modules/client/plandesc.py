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
# Copyright (c) 2012, 2016, Oracle and/or its affiliates. All rights reserved.
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
import six

import pkg.actions
import pkg.client.actuator
import pkg.client.api_errors as apx
import pkg.client.linkedimage as li
import pkg.client.pkgplan
import pkg.facet
import pkg.fmri
import pkg.misc
import pkg.version

from pkg.api_common import (PackageInfo, LicenseInfo)
from pkg.client.pkgdefs import MSG_GENERAL

UNEVALUATED       = 0 # nothing done yet
EVALUATED_PKGS    = 1 # established fmri changes
MERGED_OK         = 2 # created single merged plan
EVALUATED_OK      = 3 # ready to execute
PREEXECUTED_OK    = 4 # finished w/ preexecute
PREEXECUTED_ERROR = 5 # whoops
EXECUTED_OK       = 6 # finished execution
EXECUTED_ERROR    = 7 # failed

OP_STAGE_PLAN     = 0
OP_STAGE_PREP     = 1
OP_STAGE_EXEC     = 2

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
            "_fmri_changes": [ ( pkg.fmri.PkgFmri, pkg.fmri.PkgFmri ) ],
            # avoid, implicit-avoid, obsolete
            "_new_avoid_obs": ( set(), set(), set() ),
            "_new_mediators": collections.defaultdict(set, {
                str: {
                    "version": pkg.version.Version,
                    "implementation-version": pkg.version.Version,
                }
            }),
            "_old_facets": pkg.facet.Facets,
            "_new_facets": pkg.facet.Facets,
            "_rm_aliases": { str: set() },
            "_preserved": {
                "moved": [[str, str]],
                "removed": [[str]],
                "installed": [[str]],
                "updated": [[str]],
            },
            # Messaging looks like:
            # {"item_id": {"sub_item_id": [], "messages": []}}
            "_item_msgs": collections.defaultdict(dict),
            "_pkg_actuators": { str: { str: [ str ] } },
            "added_groups": { str: pkg.fmri.PkgFmri },
            "added_users": { str: pkg.fmri.PkgFmri },
            "child_op_vectors": [ ( str, [ li.LinkedImageName ], {}, bool ) ],
            "children_ignored": [ li.LinkedImageName ],
            "children_nop": [ li.LinkedImageName ],
            "children_planned": [ li.LinkedImageName ],
            "install_actions": [ _ActionPlan ],
            "li_pfacets": pkg.facet.Facets,
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
                self._old_facets = None
                self._new_facets = None
                self._facet_change = False
                self._masked_facet_change = False
                self._new_mediators = collections.defaultdict(set)
                self._mediators_change = False
                self._new_avoid_obs = (set(), set(), set())
                self._fmri_changes = [] # install  (None, fmri)
                                        # remove   (oldfmri, None)
                                        # update   (oldfmri, newfmri|oldfmri)
                self._preserved = {
                    "moved": [],
                    "removed": [],
                    "installed": [],
                    "updated": [],
                }
                self._solver_summary = []
                self._solver_errors = None
                self.li_attach = False
                self.li_ppkgs = frozenset()
                self.li_ppubs = None
                self.li_props = {}
                self._li_pkg_updates = True
                self._item_msgs = collections.defaultdict(dict)

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
                self.child_op_vectors = []
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

                self._act_timed_out = False

                # Pkg actuators
                self._pkg_actuators = {}

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
                except OSError as e:
                        # Access to protected member; pylint: disable=W0212
                        raise apx._convert_error(e)

                del state

        def _load(self, fobj):
                """Load a json encoded representation of a plan description
                from the specified file object."""

                assert self.state == UNEVALUATED

                try:
                        fobj.seek(0)
                        state = json.load(fobj, encoding="utf-8",
                            object_hook=pkg.misc.json_hook)
                except OSError as e:
                        # Access to protected member; pylint: disable=W0212
                        raise apx._convert_error(e)

                PlanDescription.setstate(self, state)
                del state

        def _executed_ok(self):
                """A private interface used after a plan is successfully
                invoked to free up memory."""

                # reduce memory consumption
                self._fmri_changes = []
                self._preserved = {}
                # We have to save the timed_out state.
                self._act_timed_out = self._actuators.timed_out
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
                                        mimpl += "(@{0})".format(mimpl_ver)
                                mimpl_source = mediators[m].get(
                                    "implementation-source")

                                mver = mediators[m].get("version")
                                if mver:
                                        mver = mver.get_short_version()
                                mver_source = mediators[m].get(
                                    "version-source")
                        return mimpl, mver, mimpl_source, mver_source

                for m in sorted(set(list(self._new_mediators.keys()) +
                    list(self._cfg_mediators.keys()))):
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
                        out = "mediator {0}:\n".format(m)
                        if orig_ver and new_ver:
                                out += "           version: {0} ({1} default)" \
                                    " -> {2} ({3} default)\n".format(orig_ver,
                                    orig_ver_source, new_ver, new_ver_source)
                        elif orig_ver:
                                out += "           version: {0} ({1} default)" \
                                    " -> None\n".format(orig_ver,
                                    orig_ver_source)
                        elif new_ver:
                                out += "           version: None -> " \
                                    "{0} ({1} default)\n".format(new_ver,
                                    new_ver_source)

                        if orig_impl and new_impl:
                                out += "    implementation: {0} ({1} default)" \
                                    " -> {2} ({3} default)\n".format(orig_impl,
                                    orig_impl_source, new_impl, new_impl_source)
                        elif orig_impl:
                                out += "    implementation: {0} ({1} default)" \
                                    " -> None\n".format(orig_impl,
                                    orig_impl_source)
                        elif new_impl:
                                out += "    implementation: None -> " \
                                    "{0} ({1} default)\n".format(new_impl,
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
                return self._salvaged

        @property
        def varcets(self):
                """Returns a tuple of two lists containing the facet and
                variant changes in this plan.

                The variant list contains tuples with the following format:

                    (<variant>, <new-value>)

                The facet list contains tuples with the following format:

                    (<facet>, <new-value>, <old-value>, <source>,
                        <new-masked>, <old-masked>)

                """

                vs = []
                if self._new_variants:
                        vs = list(self._new_variants.items())

                # sort results by variant name
                vs.sort(key=lambda x: x[0])

                fs = []
                if self._new_facets is None:
                        return (vs, fs)

                # create new dictionaries that index facets by name and
                # source:
                #    dict[(<facet, src>)] = (<value>, <masked>)
                old_facets = dict([
                    ((f, src), (v, masked))
                    for f in self._old_facets
                    # W0212 Access to a protected member
                    # pylint: disable=W0212
                    for v, src, masked in self._old_facets._src_values(f)
                ])
                new_facets = dict([
                    ((f, src), (v, masked))
                    for f in self._new_facets
                    # W0212 Access to a protected member
                    # pylint: disable=W0212
                    for v, src, masked in self._new_facets._src_values(f)
                ])

                # check for removed facets
                for f, src in set(old_facets) - set(new_facets):
                        v, masked = old_facets[f, src]
                        fs.append((f, None, v, src, masked, False))

                # check for added facets
                for f, src in set(new_facets) - set(old_facets):
                        v, masked = new_facets[f, src]
                        fs.append((f, v, None, src, False, masked))

                # check for changing facets
                for f, src in set(old_facets) & set(new_facets):
                        if old_facets[f, src] == new_facets[f, src]:
                                continue
                        v_old, m_old = old_facets[f, src]
                        v_new, m_new = new_facets[f, src]
                        fs.append((f, v_new, v_old, src, m_old, m_new))

                # sort results by facet name
                fs.sort(key=lambda x: x[0])

                return (vs, fs)

        def get_varcets(self):
                """Returns a formatted list of strings representing the
                variant/facet changes in this plan"""
                vs, fs = self.varcets
                rv = [
                    "variant {0}: {1}".format(name[8:], val)
                    for (name, val) in vs
                ]
                masked_str = _(" (masked)")
                for name, v_new, v_old, src, m_old, m_new in fs:
                        m_old = m_old and masked_str or ""
                        m_new = m_new and masked_str or ""
                        msg = "  facet {0} ({1}): {2}{3} -> {4}{5}".format(
                            name[6:], src, v_old, m_old, v_new, m_new)
                        rv.append(msg)
                return rv

        def get_changes(self):
                """A generator function that yields tuples of PackageInfo
                objects of the form (src_pi, dest_pi).

                If 'src_pi' is None, then 'dest_pi' is the package being
                installed.

                If 'src_pi' is not None, and 'dest_pi' is None, 'src_pi'
                is the package being removed.

                If 'src_pi' is not None, and 'dest_pi' is not None,
                then 'src_pi' is the original version of the package,
                and 'dest_pi' is the new version of the package it is
                being upgraded to."""

                key = operator.attrgetter("origin_fmri", "destination_fmri")
                for pp in sorted(self.pkg_plans, key=key):
                        sfmri = pp.origin_fmri
                        dfmri = pp.destination_fmri
                        if sfmri == dfmri:
                                sinfo = dinfo = PackageInfo.build_from_fmri(
                                    sfmri)
                        else:
                                sinfo = PackageInfo.build_from_fmri(sfmri)
                                dinfo = PackageInfo.build_from_fmri(dfmri)
                        yield (sinfo, dinfo)

        def get_editable_changes(self):
                """This function returns a tuple of generators that yield tuples
                of the form (src, dest) of the preserved ("editable") files that
                will be installed, moved, removed, or updated.  The returned
                list of generators is (moved, removed, installed, updated)."""

                return (
                    (entry for entry in self._preserved["moved"]),
                    ((entry[0], None) for entry in self._preserved["removed"]),
                    ((None, entry[0])
                        for entry in self._preserved["installed"]),
                    ((entry[0], entry[0])
                        for entry in self._preserved["updated"]),
                )

        def get_actions(self):
                """A generator function that yields action change descriptions
                in the order they will be performed."""

                # Unused variable '%s'; pylint: disable=W0612
                for pplan, o_act, d_act in itertools.chain(
                    self.removal_actions,
                    self.update_actions,
                    self.install_actions):
                # pylint: enable=W0612
                        yield "{0} -> {1}".format(o_act, d_act)

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
                        "{0} >= {1}".format(self.state, EVALUATED_PKGS)

                # in case this operation doesn't use solver
                if self._solver_errors is None:
                        return []

                return self._solver_errors

        def get_parsable_plan(self, parsable_version, child_images=None,
            api_inst=None):
                """Display the parsable version of the plan."""

                assert parsable_version == 0, \
                    "parsable_version was {0!r}".format(parsable_version)
                # Set the default values.
                added_fmris = []
                removed_fmris = []
                changed_fmris = []
                affected_fmris = []
                backup_be_created = False
                new_be_created = False
                backup_be_name = None
                be_name = None
                boot_archive_rebuilt = False
                be_activated = True
                space_available = None
                space_required = None
                facets_changed = []
                variants_changed = []
                services_affected = []
                mediators_changed = []
                editables_changed = []
                licenses = []

                if child_images is None:
                        child_images = []
                release_notes = []
                if self:
                        for rem, add in self.get_changes():
                                assert rem is not None or add is not None
                                if rem is not None and add is not None:
                                        # Lists of lists are used here becuase
                                        # json will convert lists of tuples
                                        # into lists of lists anyway.
                                        if rem.fmri == add.fmri:
                                                affected_fmris.append(str(rem))
                                        else:
                                                changed_fmris.append(
                                                    [str(rem), str(add)])
                                elif rem is not None:
                                        removed_fmris.append(str(rem))
                                else:
                                        added_fmris.append(str(add))
                        variants_changed, facets_changed = self.varcets
                        backup_be_created = self.backup_be
                        new_be_created = self.new_be
                        backup_be_name = self.backup_be_name
                        be_name = self.be_name
                        boot_archive_rebuilt = self.update_boot_archive
                        be_activated = self.activate_be
                        space_available = self.bytes_avail
                        space_required = self.bytes_added
                        services_affected = self.services
                        mediators_changed = self.mediators

                        emoved, eremoved, einstalled, eupdated = \
                            self.get_editable_changes()

                        # Lists of lists are used here to ensure a consistent
                        # ordering and because tuples will be converted to
                        # lists anyway; a dictionary would be more logical for
                        # the top level entries, but would make testing more
                        # difficult and this is a small, known set anyway.
                        emoved = [[e for e in entry] for entry in emoved]
                        eremoved = [src for (src, dest) in eremoved]
                        einstalled = [dest for (src, dest) in einstalled]
                        eupdated = [dest for (src, dest) in eupdated]
                        if emoved:
                                editables_changed.append(["moved", emoved])
                        if eremoved:
                                editables_changed.append(["removed", eremoved])
                        if einstalled:
                                editables_changed.append(["installed",
                                    einstalled])
                        if eupdated:
                                editables_changed.append(["updated", eupdated])

                        for n in self.get_release_notes():
                                release_notes.append(n)

                        for dfmri, src_li, dest_li, dummy_acc, dummy_disp in \
                            self.get_licenses():
                                src_tup = ()
                                if src_li:
                                        li_txt = pkg.misc.decode(
                                            src_li.get_text())
                                        src_tup = (str(src_li.fmri),
                                            src_li.license, li_txt,
                                            src_li.must_accept,
                                            src_li.must_display)
                                dest_tup = ()
                                if dest_li:
                                        li_txt = pkg.misc.decode(
                                            dest_li.get_text())
                                        dest_tup = (str(dest_li.fmri),
                                            dest_li.license, li_txt,
                                            dest_li.must_accept,
                                            dest_li.must_display)
                                licenses.append(
                                    (str(dfmri), src_tup, dest_tup))

                                # If api_inst is set, mark licenses as
                                # displayed.
                                if api_inst:
                                        api_inst.set_plan_license_status(dfmri,
                                            dest_li.license, displayed=True)

                # The image name for the parent image is always None.  If this
                # image is a child image, then the image name will be set when
                # the parent image processes this dictionary.
                ret = {
                    "activate-be": be_activated,
                    "add-packages": sorted(added_fmris),
                    "affect-packages": sorted(affected_fmris),
                    "affect-services": sorted(services_affected),
                    "backup-be-name": backup_be_name,
                    "be-name": be_name,
                    "boot-archive-rebuild": boot_archive_rebuilt,
                    "change-facets": sorted(facets_changed),
                    "change-editables": editables_changed,
                    "change-mediators": sorted(mediators_changed),
                    "change-packages": sorted(changed_fmris),
                    "change-variants": sorted(variants_changed),
                    "child-images": child_images,
                    "create-backup-be": backup_be_created,
                    "create-new-be": new_be_created,
                    "image-name": None,
                    "item-messages": self.get_parsable_item_messages(),
                    "licenses": sorted(licenses,
                        key=lambda x: (x[0], x[1], x[2])),
                    "release-notes": release_notes,
                    "remove-packages": sorted(removed_fmris),
                    "space-available": space_available,
                    "space-required": space_required,
                    "version": parsable_version
                }
                return ret

        def get_parsable_item_messages(self):
                """Return parsable item messages."""
                return self._item_msgs

        def add_item_message(self, item_id, msg_time, msg_level, msg_text,
            msg_type=MSG_GENERAL, parent=None):
                """Add a new message with its time, type and text for an
                item."""
                if parent:
                        item_key = parent
                        sub_item = item_id
                else:
                        item_key = item_id
                        sub_item = "messages"
                if self.state >= PREEXECUTED_OK:
                        msg_stage = OP_STAGE_EXEC
                elif self.state >= EVALUATED_OK:
                        msg_stage = OP_STAGE_PREP
                else:
                        msg_stage = OP_STAGE_PLAN
                # First level messaging looks like:
                # {"item_id": {"messages": [msg_payload ...]}}
                # Second level messaging looks like:
                # {"item_id": {"sub_item_id": [msg_payload ...]}}.
                msg_payload = {"msg_time": msg_time,
                               "msg_level": msg_level,
                               "msg_type": msg_type,
                               "msg_text": msg_text,
                               "msg_stage": msg_stage}
                self._item_msgs[item_key].setdefault(sub_item,
                    []).append(msg_payload)

        def extend_item_messages(self, item_id, messages, parent=None):
                """Add new messages to an item."""
                if parent:
                        item_key = parent
                        sub_item = item_id
                else:
                        item_key = item_id
                        sub_item = "messages"
                self._item_msgs[item_key].setdefault(sub_item, []).extend(
                    messages)

        @staticmethod
        def __msg_dict2list(msg):
                """Convert a message dictionary to a list."""
                return [msg["msg_time"], msg["msg_level"], msg["msg_type"],
                    msg["msg_text"]]

        def __gen_ordered_msg(self, stages):
                """Generate ordered messages."""
                ordered_list = []
                for item_id in self._item_msgs:
                        # To make the first level messages come
                        # relatively earlier.
                        if "messages" in self._item_msgs[item_id]:
                                for msg in self._item_msgs[item_id]["messages"]:
                                        if (stages is not None and
                                            msg["msg_stage"] not in stages):
                                                continue
                                        ordered_list.append([item_id, None] + \
                                            PlanDescription. \
                                                    __msg_dict2list(msg))
                        for si, si_list in six.iteritems(
                            self._item_msgs[item_id]):
                                if si == "messages":
                                        continue
                                for msg in si_list:
                                        if (stages is not None and
                                            msg["msg_stage"] not in stages):
                                                continue
                                        ordered_list.append([si, item_id] + \
                                            PlanDescription. \
                                                    __msg_dict2list(msg))
                for entry in sorted(ordered_list, key=operator.itemgetter(2)):
                        yield entry

        def __gen_unordered_msg(self, stages):
                """Generate unordered messages."""
                for item_id in self._item_msgs:
                        for si, si_list in six.iteritems(
                            self._item_msgs[item_id]):
                                if si == "messages":
                                        iid = item_id
                                        pid = None
                                else:
                                        iid = si
                                        pid = item_id
                                for mp in si_list:
                                        if (stages is not None and
                                            mp["msg_stage"] not in stages):
                                                continue
                                        yield([iid, pid] + \
                                            PlanDescription.__msg_dict2list(mp))

        def gen_item_messages(self, ordered=False, stages=None):
                """Return all item messages.

                'ordered' is an optional boolean value that indicates that
                item messages will be sorted by msg_time. If False, item
                messages will be in an arbitrary order.

                'stages' is an optional list or set of the stages of messages
                to return."""

                if ordered:
                        return self.__gen_ordered_msg(stages)
                else:
                        return self.__gen_unordered_msg(stages)

        def set_actuator_timeout(self, timeout):
                """Set timeout for synchronous actuators."""
                assert type(timeout) == int, "Actuator timeout must be an "\
                    "integer."
                self._actuators.set_timeout(timeout)

        def add_pkg_actuator(self, trigger_pkg, exec_op, cpkg):
                """Add a pkg actuator to the plan. The internal dictionary looks
                like this:
                        {  trigger_pkg: {
                                          exec_op : [ changed pkg, ... ],
                                          ...
                                        },
                          ...
                        }
                """

                if trigger_pkg in self._pkg_actuators:
                        if exec_op in self._pkg_actuators[trigger_pkg]:
                                self._pkg_actuators[trigger_pkg][
                                    exec_op].append(cpkg)
                                self._pkg_actuators[trigger_pkg][exec_op].sort()
                        else:
                                self._pkg_actuators[trigger_pkg][exec_op] = \
                                    [cpkg]
                else:
                        self._pkg_actuators[trigger_pkg] = {exec_op: [cpkg]}

        def gen_pkg_actuators(self):
                """Pkg actuators which got triggered by operation."""
                for trigger_pkg in sorted(self._pkg_actuators):
                        yield (trigger_pkg, self._pkg_actuators[trigger_pkg])

        @property
        def actuator_timed_out(self):
                """Indicates that a synchronous actuator timed out."""
                return self._act_timed_out

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

        @property
        def new_facets(self):
                """If facets are changing, this is the new set of facets being
                applied."""
                if self._new_facets is None:
                        return None
                return pkg.facet.Facets(self._new_facets)
