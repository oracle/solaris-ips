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
# Copyright (c) 2007, 2015, Oracle and/or its affiliates. All rights reserved.
#

import copy
import grp
import itertools
import os
import pwd
import six
import stat

import pkg.actions
import pkg.actions.directory as directory
import pkg.client.api_errors as apx
import pkg.fmri
import pkg.manifest as manifest
import pkg.misc

from functools import reduce

from pkg.client import global_settings
from pkg.misc import expanddirs, get_pkg_otw_size, EmptyI

logger = global_settings.logger

class PkgPlan(object):
        """A package plan takes two package FMRIs and an Image, and produces the
        set of actions required to take the Image from the origin FMRI to the
        destination FMRI.

        If the destination FMRI is None, the package is removed.
        """

        __slots__ = [
            "__destination_mfst",
            "_executed",
            "_license_status",
            "__origin_mfst",
            "__repair_actions",
            "__xferfiles",
            "__xfersize",
            "_autofix_pkgs",
            "_hash",
            "actions",
            "destination_fmri",
            "image",
            "origin_fmri",
            "pkg_summary",
        ]

        #
        # we don't serialize __xferfiles or __xfersize since those should be
        # recalculated after after a plan is loaded (since the contents of the
        # download cache may have changed).
        #
        # we don't serialize __origin_mfst, __destination_mfst, or
        # __repair_actions since we only support serializing pkgplans which
        # have had their actions evaluated and merged, and when action
        # evaluation is complete these fields are cleared.
        #
        # we don't serialize our image object pointer.  that has to be reset
        # after this object is reloaded.
        #
        __state__noserialize = frozenset([
                "__destination_mfst",
                "__origin_mfst",
                "__repair_actions",
                "__xferfiles",
                "__xfersize",
                "image",
        ])

        # make sure all __state__noserialize values are valid
        assert (__state__noserialize - set(__slots__)) == set()

        # figure out which state we are saving.
        __state__serialize = set(__slots__) - __state__noserialize

        # describe our state and the types of all objects
        __state__desc = {
            "_autofix_pkgs": [ pkg.fmri.PkgFmri ],
            "_license_status": {
                six.string_types[0]: {
                    "src": pkg.actions.generic.NSG,
                    "dest": pkg.actions.generic.NSG,
                },
            },
            "actions": pkg.manifest.ManifestDifference,
            "destination_fmri": pkg.fmri.PkgFmri,
            "origin_fmri": pkg.fmri.PkgFmri,
        }

        __state__commonize = frozenset([
            pkg.fmri.PkgFmri,
        ])

        def __init__(self, image=None):
                self.destination_fmri = None
                self.__destination_mfst = manifest.NullFactoredManifest

                self.origin_fmri = None
                self.__origin_mfst = manifest.NullFactoredManifest

                self.actions = manifest.ManifestDifference([], [], [])
                self.image = image
                self.pkg_summary = None

                self._executed = False
                self._license_status = {}
                self.__repair_actions = {}
                self.__xferfiles = -1
                self.__xfersize = -1
                self._autofix_pkgs = []
                self._hash = None

        @staticmethod
        def getstate(obj, je_state=None):
                """Returns the serialized state of this object in a format
                that that can be easily stored using JSON, pickle, etc."""

                # validate unserialized state
                # (see comments above __state__noserialize)
                assert obj.__origin_mfst == manifest.NullFactoredManifest
                assert obj.__destination_mfst == manifest.NullFactoredManifest
                assert obj.__repair_actions == {}

                # we use __slots__, so create a state dictionary
                state = {}
                for k in obj.__state__serialize:
                        state[k] = getattr(obj, k)

                return pkg.misc.json_encode(PkgPlan.__name__, state,
                    PkgPlan.__state__desc,
                    commonize=PkgPlan.__state__commonize, je_state=je_state)

        @staticmethod
        def setstate(obj, state, jd_state=None):
                """Update the state of this object using previously serialized
                state obtained via getstate()."""

                # get the name of the object we're dealing with
                name = type(obj).__name__

                # decode serialized state into python objects
                state = pkg.misc.json_decode(name, state,
                    PkgPlan.__state__desc,
                    commonize=PkgPlan.__state__commonize,
                    jd_state=jd_state)

                # we use __slots__, so directly update attributes
                for k in state:
                        setattr(obj, k, state[k])

                # update unserialized state
                # (see comments above __state__noserialize)
                obj.__origin_mfst = manifest.NullFactoredManifest
                obj.__destination_mfst = manifest.NullFactoredManifest
                obj.__repair_actions = {}
                obj.__xferfiles = -1
                obj.__xfersize = -1
                obj.image = None

        @staticmethod
        def fromstate(state, jd_state=None):
                """Allocate a new object using previously serialized state
                obtained via getstate()."""
                rv = PkgPlan()
                PkgPlan.setstate(rv, state, jd_state)
                return rv

        def __str__(self):
                s = "{0} -> {1}\n".format(self.origin_fmri,
                    self.destination_fmri)
                for src, dest in itertools.chain(*self.actions):
                        s += "  {0} -> {1}\n".format(src, dest)
                return s

        def __add_license(self, src, dest):
                """Adds a license status entry for the given src and dest
                license actions.

                'src' should be None or the source action for a license.

                'dest' must be the destination action for a license."""

                self._license_status[dest.attrs["license"]] = {
                    "src": src,
                    "dest": dest,
                    "accepted": False,
                    "displayed": False,
                }

        def propose(self, of, om, df, dm):
                """Propose origin and dest fmri, manifest"""
                self.origin_fmri = of
                self.__origin_mfst = om
                self.destination_fmri = df
                self.__destination_mfst = dm

        def __get_orig_act(self, dest):
                """Generate the on-disk state (attributes) of the action
                that fail verification."""

                if not dest.has_payload or "path" not in dest.attrs:
                        return

                path = os.path.join(self.image.root, dest.attrs["path"])
                try:
                        pstat = os.lstat(path)
                except Exception:
                        # If file to repair isn't on-disk, treat as install
                        return

                act = pkg.actions.fromstr(str(dest))
                act.attrs["mode"] = oct(stat.S_IMODE(pstat.st_mode))
                try:
                        owner = pwd.getpwuid(pstat.st_uid).pw_name
                        group = grp.getgrgid(pstat.st_gid).gr_name
                except KeyError:
                        # If associated user / group can't be determined, treat
                        # as install. This is not optimal for repairs, but
                        # ensures proper ownership of file is set.
                        return
                act.attrs["owner"] = owner
                act.attrs["group"] = group

                # No need to generate hash of on-disk content as verify
                # short-circuits hash comparison by setting replace_required
                # flag on action.  The same is true for preserved files which
                # will automatically handle content replacement if needed based
                # on the result of _check_preserve.
                return act

        def propose_repair(self, fmri, mfst, install, remove, autofix=False):
                self.propose(fmri, mfst, fmri, mfst)
                # self.origin_fmri = None
                # I'd like a cleaner solution than this; we need to actually
                # construct a list of actions as things currently are rather
                # than just re-applying the current set of actions.
                #
                # Create a list of (src, dst) pairs for the actions to send to
                # execute_repair.

                if autofix:
                        # If an uninstall causes a fixup to happen, we can't
                        # generate an on-disk state action because the result
                        # of needsdata is different between propose and execute.
                        # Therefore, we explicitly assign None to src for actions
                        # to be installed.
                        self.__repair_actions = {
                            # src is none for repairs
                            "install": [(None, x) for x in install],
                            # dest is none for removals.
                            "remove": [(x, None) for x in remove],
                        }
                        self._autofix_pkgs.append(fmri)
                else:
                        self.__repair_actions = {
                            # src can be None or an action representing on-disk state
                            "install": [(self.__get_orig_act(x), x) for x in install],
                            "remove": [(x, None) for x in remove],
                        }

        def get_actions(self):
                raise NotImplementedError()

        def get_nactions(self):
                return len(self.actions.added) + len(self.actions.changed) + \
                    len(self.actions.removed)

        def update_pkg_set(self, fmri_set):
                """ updates a set of installed fmris to reflect
                proposed new state"""

                if self.origin_fmri:
                        fmri_set.discard(self.origin_fmri)

                if self.destination_fmri:
                        fmri_set.add(self.destination_fmri)

        def evaluate(self, old_excludes=EmptyI, new_excludes=EmptyI,
            can_exclude=False):
                """Determine the actions required to transition the package."""

                # If new actions are being installed, check the destination
                # manifest for signatures.
                if self.destination_fmri is not None:
                        try:
                                dest_pub = self.image.get_publisher(
                                    prefix=self.destination_fmri.publisher)
                        except apx.UnknownPublisher:
                                # Since user removed publisher, assume this is
                                # the same as if they had set signature-policy
                                # ignore for the publisher.
                                sig_pol = None
                        else:
                                sig_pol = self.image.signature_policy.combine(
                                    dest_pub.signature_policy)

                        if self.destination_fmri in self._autofix_pkgs:
                                # Repaired packages use a manifest synthesized
                                # from the installed one; so retrieve the
                                # installed one for our signature checks.
                                sigman = self.image.get_manifest(
                                    self.destination_fmri,
                                    ignore_excludes=True)
                        else:
                                sigman = self.__destination_mfst

                        sigs = list(sigman.gen_actions_by_type("signature",
                            excludes=new_excludes))
                        if sig_pol and (sigs or sig_pol.name != "ignore"):
                                # Only perform signature verification logic if
                                # there are signatures or if signature-policy
                                # is not 'ignore'.

                                try:
                                        sig_pol.process_signatures(sigs,
                                            sigman.gen_actions(),
                                            dest_pub, self.image.trust_anchors,
                                            self.image.cfg.get_policy(
                                                "check-certificate-revocation"))
                                except apx.SigningException as e:
                                        e.pfmri = self.destination_fmri
                                        if isinstance(e, apx.BrokenChain):
                                                e.ext_exs.extend(
                                                    self.image.bad_trust_anchors
                                                    )
                                        raise
                if can_exclude:
                        if self.__destination_mfst is not None:
                                self.__destination_mfst.exclude_content(
                                    new_excludes)
                        if self.__origin_mfst is not None and \
                            self.__destination_mfst != self.__origin_mfst:
                                self.__origin_mfst.exclude_content(old_excludes)
                        old_excludes = EmptyI
                        new_excludes = EmptyI

                self.actions = self.__destination_mfst.difference(
                    self.__origin_mfst, old_excludes, new_excludes)

                # figure out how many implicit directories disappear in this
                # transition and add directory remove actions.  These won't
                # do anything unless no pkgs reference that directory in
                # new state....

                # Retrieving origin_dirs first and then checking it for any
                # entries allows avoiding an unnecessary expanddirs for the
                # destination manifest when it isn't needed.
                origin_dirs = expanddirs(self.__origin_mfst.get_directories(
                    old_excludes))

                # Manifest.get_directories() returns implicit directories, which
                # means that this computation ends up re-adding all the explicit
                # directories getting removed to the removed list.  This is
                # ugly, but safe.
                if origin_dirs:
                        absent_dirs = origin_dirs - \
                            expanddirs(self.__destination_mfst.get_directories(
                            new_excludes))

                        for a in absent_dirs:
                                self.actions.removed.append(
                                    (directory.DirectoryAction(path=a,
                                    implicit="True"), None))

                # Stash information needed by legacy actions.
                self.pkg_summary = \
                    self.__destination_mfst.get("pkg.summary",
                    self.__destination_mfst.get("description", "none provided"))

                # Add any install repair actions to the update list
                self.actions.changed.extend(self.__repair_actions.get("install",
                    EmptyI))
                self.actions.removed.extend(self.__repair_actions.get("remove",
                    EmptyI))

                # No longer needed.
                self.__repair_actions = {}

                for src, dest in itertools.chain(self.gen_update_actions(),
                    self.gen_install_actions()):
                        if dest.name == "license":
                                self.__add_license(src, dest)
                                if not src:
                                        # Initial installs require acceptance.
                                        continue
                                src_ma = src.attrs.get("must-accept", False)
                                dest_ma = dest.attrs.get("must-accept", False)
                                if (dest_ma and src_ma) and \
                                    src.hash == dest.hash:
                                        # If src action required acceptance,
                                        # then license was already accepted
                                        # before, and if the hashes are the
                                        # same for the license payload, then
                                        # it doesn't need to be accepted again.
                                        self.set_license_status(
                                            dest.attrs["license"],
                                            accepted=True)

        def get_licenses(self):
                """A generator function that yields tuples of the form (license,
                entry).  Where 'entry' is a dict containing the license status
                information."""

                for lic, entry in six.iteritems(self._license_status):
                        yield lic, entry

        def set_license_status(self, plicense, accepted=None, displayed=None):
                """Sets the license status for the given license entry.

                'plicense' should be the value of the license attribute for the
                destination license action.

                'accepted' is an optional parameter that can be one of three
                values:
                        None    leaves accepted status unchanged
                        False   sets accepted status to False
                        True    sets accepted status to True

                'displayed' is an optional parameter that can be one of three
                values:
                        None    leaves displayed status unchanged
                        False   sets displayed status to False
                        True    sets displayed status to True"""

                entry = self._license_status[plicense]
                if accepted is not None:
                        entry["accepted"] = accepted
                if displayed is not None:
                        entry["displayed"] = displayed

        def get_xferstats(self):
                if self.__xfersize != -1:
                        return (self.__xferfiles, self.__xfersize)

                self.__xfersize = 0
                self.__xferfiles = 0
                for src, dest in itertools.chain(*self.actions):
                        if dest and dest.needsdata(src, self):
                                self.__xfersize += get_pkg_otw_size(dest)
                                self.__xferfiles += 1
                                if dest.name == "signature":
                                        self.__xfersize += \
                                            dest.get_action_chain_csize()
                                        self.__xferfiles += \
                                            len(dest.attrs.get("chain",
                                                "").split())

                return (self.__xferfiles, self.__xfersize)

        def get_bytes_added(self):
                """Return tuple of compressed bytes possibly downloaded
                and number of bytes laid down; ignore removals
                because they're usually pinned by snapshots"""
                def sum_dest_size(a, b):
                        if b[1]:
                                return (a[0] + int(b[1].attrs.get("pkg.csize" ,0)),
                                    a[1] + int(b[1].attrs.get("pkg.size", 0)))
                        return (a[0], a[1])

                return reduce(sum_dest_size, itertools.chain(*self.actions),
                    (0, 0))

        def get_xferfmri(self):
                if self.destination_fmri:
                        return self.destination_fmri
                if self.origin_fmri:
                        return self.origin_fmri
                return None

        def preexecute(self):
                """Perform actions required prior to installation or removal of
                a package.

                This method executes each action's preremove() or preinstall()
                methods, as well as any package-wide steps that need to be taken
                at such a time.
                """

                # Determine if license acceptance requirements have been met as
                # early as possible.
                errors = []
                for lic, entry in self.get_licenses():
                        dest = entry["dest"]
                        if (dest.must_accept and not entry["accepted"]) or \
                            (dest.must_display and not entry["displayed"]):
                                errors.append(apx.LicenseAcceptanceError(
                                    self.destination_fmri, **entry))

                if errors:
                        raise apx.PkgLicenseErrors(errors)

                for src, dest in itertools.chain(*self.actions):
                        if dest:
                                dest.preinstall(self, src)
                        else:
                                src.preremove(self)

        def download(self, progtrack, check_cancel):
                """Download data for any actions that need it."""
                progtrack.download_start_pkg(self.get_xferfmri())
                mfile = self.image.transport.multi_file(self.destination_fmri,
                    progtrack, check_cancel)

                if mfile is None:
                        progtrack.download_end_pkg(self.get_xferfmri())
                        return

                for src, dest in itertools.chain(*self.actions):
                        if dest and dest.needsdata(src, self):
                                mfile.add_action(dest)

                mfile.wait_files()
                progtrack.download_end_pkg(self.get_xferfmri())

        def cacheload(self):
                """Load previously downloaded data for actions that need it."""

                fmri = self.destination_fmri
                for src, dest in itertools.chain(*self.actions):
                        if not dest or not dest.needsdata(src, self):
                                continue
                        dest.data = self.image.transport.action_cached(fmri,
                            dest)

        def gen_install_actions(self):
                for src, dest in self.actions.added:
                        yield src, dest

        def gen_removal_actions(self):
                for src, dest in self.actions.removed:
                        yield src, dest

        def gen_update_actions(self):
                for src, dest in self.actions.changed:
                        yield src, dest

        def execute_install(self, src, dest):
                """ perform action for installation of package"""
                self._executed = True
                try:
                        dest.install(self, src)
                except (pkg.actions.ActionError, EnvironmentError):
                        # Don't log these as they're expected, and should be
                        # handled by the caller.
                        raise
                except Exception as e:
                        logger.error("Action install failed for '{0}' ({1}):\n  "
                            "{2}: {3}".format(dest.attrs.get(dest.key_attr,
                            id(dest)), self.destination_fmri.get_pkg_stem(),
                            e.__class__.__name__, e))
                        raise

        def execute_update(self, src, dest):
                """ handle action updates"""
                self._executed = True
                try:
                        dest.install(self, src)
                except (pkg.actions.ActionError, EnvironmentError):
                        # Don't log these as they're expected, and should be
                        # handled by the caller.
                        raise
                except Exception as e:
                        logger.error("Action upgrade failed for '{0}' ({1}):\n "
                            "{2}: {3}".format(dest.attrs.get(dest.key_attr,
                            id(dest)), self.destination_fmri.get_pkg_stem(),
                            e.__class__.__name__, e))
                        raise

        def execute_removal(self, src, dest):
                """ handle action removals"""
                self._executed = True
                try:
                        src.remove(self)
                except (pkg.actions.ActionError, EnvironmentError):
                        # Don't log these as they're expected, and should be
                        # handled by the caller.
                        raise
                except Exception as e:
                        logger.error("Action removal failed for '{0}' ({1}):\n "
                            "{2}: {3}".format(src.attrs.get(src.key_attr,
                            id(src)), self.origin_fmri.get_pkg_stem(),
                            e.__class__.__name__, e))
                        raise

        def execute_retry(self, src, dest):
                """handle a retry operation"""
                dest.retry(self, dest)

        def postexecute(self):
                """Perform actions required after install or remove of a pkg.

                This method executes each action's postremove() or postinstall()
                methods, as well as any package-wide steps that need to be taken
                at such a time.
                """
                # record that package states are consistent
                for src, dest in itertools.chain(*self.actions):
                        if dest:
                                dest.postinstall(self, src)
                        else:
                                src.postremove(self)

        def salvage(self, path):
                """Used to save unexpected files or directories found during
                plan execution.  Salvaged items are tracked in the imageplan.
                """

                assert self._executed
                spath = self.image.salvage(path)
                # get just the file path that was salvaged
                fpath = path.replace(
                    os.path.normpath(self.image.get_root()), "", 1)
                if fpath.startswith(os.path.sep):
                        fpath = fpath[1:]
                self.image.imageplan.pd._salvaged.append((fpath, spath))

        def salvage_from(self, local_path, full_destination):
                """move unpackaged contents to specified destination"""
                # remove leading / if present
                if local_path.startswith(os.path.sep):
                        local_path = local_path[1:]

                for fpath, spath in self.image.imageplan.pd._salvaged[:]:
                        if fpath.startswith(local_path):
                                self.image.imageplan.pd._salvaged.remove((fpath, spath))
                                break
                else:
                        return

                self.image.recover(spath, full_destination)

        @property
        def destination_manifest(self):
                return self.__destination_mfst

        def clear_dest_manifest(self):
                self.__destination_mfst = manifest.NullFactoredManifest

        @property
        def origin_manifest(self):
                return self.__origin_mfst

        def clear_origin_manifest(self):
                self.__origin_mfst = manifest.NullFactoredManifest
