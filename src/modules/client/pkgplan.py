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
# Copyright (c) 2007, 2011, Oracle and/or its affiliates.  All rights reserved.
#

import itertools
import cPickle as pickle

from pkg.client import global_settings
logger = global_settings.logger

import pkg.actions
import pkg.actions.directory as directory
import pkg.client.api_errors as apx
import pkg.manifest as manifest
from pkg.misc import expanddirs, get_pkg_otw_size, EmptyI

import os.path

class PkgPlan(object):
        """A package plan takes two package FMRIs and an Image, and produces the
        set of actions required to take the Image from the origin FMRI to the
        destination FMRI.

        If the destination FMRI is None, the package is removed.
        """

        __slots__ = [
            "actions", "check_cancelation", "destination_fmri", "image",
            "origin_fmri", "pkg_summary", "__destination_mfst",
            "__license_status", "__origin_mfst", "__progtrack",
            "__repair_actions", "__xferfiles", "__xfersize",
            "_autofix_pkgs", "__executed"
        ]

        def __init__(self, image, progtrack, check_cancelation):
                self.destination_fmri = None
                self.__destination_mfst = manifest.NullFactoredManifest

                self.origin_fmri = None
                self.__origin_mfst = manifest.NullFactoredManifest

                self.actions = manifest.ManifestDifference([], [], [])
                self.check_cancelation = check_cancelation
                self.image = image
                self.pkg_summary = None

                self.__executed = False
                self.__license_status = {}
                self.__progtrack = progtrack
                self.__repair_actions = {}
                self.__xferfiles = -1
                self.__xfersize = -1
                self._autofix_pkgs = []

        def __str__(self):
                s = "%s -> %s\n" % (self.origin_fmri, self.destination_fmri)
                for src, dest in itertools.chain(*self.actions):
                        s += "  %s -> %s\n" % (src, dest)
                return s

        def __add_license(self, src, dest):
                """Adds a license status entry for the given src and dest
                license actions.

                'src' should be None or the source action for a license.

                'dest' must be the destination action for a license."""

                self.__license_status[dest.attrs["license"]] = {
                    "src": src,
                    "dest": dest,
                    "accepted": False,
                    "displayed": False,
                }

        @staticmethod
        def __pickle_actions(actions):
                """Return a list of pickled actions."""
                action_list = []
                for pair in actions:
                        newpair = [None, None]
                        if pair[0]:
                                newpair[0] = pickle.dumps(pair[0])
                        if pair[1]:
                                newpair[1] = pickle.dumps(pair[1])
                        action_list.append(newpair)
                return action_list

        @staticmethod
        def __unpickle_actions(pickled_actions):
                """Return a list of unpickled actions."""
                action_list = []
                for pair in pickled_actions:
                        newpair = [None, None]
                        if pair[0]:
                                newpair[0] = pickle.loads(str(pair[0]))
                        if pair[1]:
                                newpair[1] = pickle.loads(str(pair[1]))
                        action_list.append(newpair)
                return action_list

        def setstate(self, state):
                """Update the state of this object using the contents of
                the supplied dictionary."""

                import pkg.fmri

                # if there is no origin, don't allocate an fmri obj
                if state["src"]:
                        state["src"] = pkg.fmri.PkgFmri(state["src"])

                # if there is no destination, don't allocate an fmri obj
                if state["dst"]:
                        state["dst"] = pkg.fmri.PkgFmri(state["dst"])

                self.origin_fmri = state["src"]
                self.destination_fmri = state["dst"]
                self.pkg_summary = state["summary"]
                self.actions = manifest.ManifestDifference([], [], [])
                self.actions.added.extend(
                    self.__unpickle_actions(state["add"]))
                self.actions.changed.extend(
                    self.__unpickle_actions(state["change"]))
                self.actions.removed.extend(
                    self.__unpickle_actions(state["remove"]))
                for src, dest in itertools.chain(self.gen_update_actions(),
                    self.gen_install_actions()):
                        if dest.name == "license":
                                self.__add_license(src, dest)

        def getstate(self):
                """Returns a dictionary containing the state of this object
                so that it can be easily stored using JSON, pickle, etc."""

                state = {}
                state["src"] = self.origin_fmri
                state["dst"] = self.destination_fmri
                state["summary"] = self.pkg_summary
                state["add"] = self.__pickle_actions(self.actions.added)
                state["change"] = self.__pickle_actions(self.actions.changed)
                state["remove"] = self.__pickle_actions(self.actions.removed)
                return state

        def propose(self, of, om, df, dm):
                """Propose origin and dest fmri, manifest"""
                self.origin_fmri = of
                self.__origin_mfst = om
                self.destination_fmri = df
                self.__destination_mfst = dm

        def propose_repair(self, fmri, mfst, install, remove, autofix=False):
                self.propose(fmri, mfst, fmri, mfst)
                # self.origin_fmri = None
                # I'd like a cleaner solution than this; we need to actually
                # construct a list of actions as things currently are rather
                # than just re-applying the current set of actions.
                #
                # Create a list of (src, dst) pairs for the actions to send to
                # execute_repair.

                self.__repair_actions = {
                    # src is none for repairs.
                    "install": [(None, x) for x in install],
                    # dest is none for removals.
                    "remove": [(x, None) for x in remove],
                }

                if autofix:
                        self._autofix_pkgs.append(fmri)

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

        def evaluate(self, old_excludes=EmptyI, new_excludes=EmptyI):
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

                        sigs = list(self.__destination_mfst.gen_actions_by_type(
                            "signature", new_excludes))
                        if sig_pol and (sigs or sig_pol.name != "ignore"):
                                # Only perform signature verification logic if
                                # there are signatures or if signature-policy
                                # is not 'ignore'.

                                try:
                                        sig_pol.process_signatures(sigs,
                                            self.__destination_mfst.gen_actions(),
                                            dest_pub, self.image.trust_anchors,
                                            self.image.cfg.get_policy(
                                                "check-certificate-revocation"))
                                        self.__destination_mfst.exclude_content(
                                            new_excludes)
                                except apx.SigningException, e:
                                        e.pfmri = self.destination_fmri
                                        raise

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

                # No longer needed.
                self.__origin_mfst = None

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
                                    [directory.DirectoryAction(path=a), None])

                # Stash information needed by legacy actions.
                self.pkg_summary = \
                    self.__destination_mfst.get("pkg.summary",
                    self.__destination_mfst.get("description", "none provided"))

                # No longer needed.
                self.__destination_mfst = None

                # Add any install repair actions to the update list
                self.actions.changed.extend(self.__repair_actions.get("install",
                    EmptyI))
                self.actions.removed.extend(self.__repair_actions.get("remove",
                    EmptyI))

                # No longer needed.
                self.__repair_actions = None

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

                for lic, entry in self.__license_status.iteritems():
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

                entry = self.__license_status[plicense]
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

        def get_xfername(self):
                if self.destination_fmri:
                        return self.destination_fmri.get_name()
                if self.origin_fmri:
                        return self.origin_fmri.get_name()
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

        def download(self):
                """Download data for any actions that need it."""
                self.__progtrack.download_start_pkg(self.get_xfername())
                mfile = self.image.transport.multi_file(self.destination_fmri,
                    self.__progtrack, self.check_cancelation)

                if mfile is None:
                        self.__progtrack.download_end_pkg()
                        return

                for src, dest in itertools.chain(*self.actions):
                        if dest and dest.needsdata(src, self):
                                mfile.add_action(dest)

                mfile.wait_files()
                self.__progtrack.download_end_pkg()

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
                self.__executed = True
                try:
                        dest.install(self, src)
                except (pkg.actions.ActionError, EnvironmentError):
                        # Don't log these as they're expected, and should be
                        # handled by the caller.
                        raise
                except Exception, e:
                        logger.error("Action install failed for '%s' (%s):\n  "
                            "%s: %s" % (dest.attrs.get(dest.key_attr, id(dest)),
                             self.destination_fmri.get_pkg_stem(),
                             e.__class__.__name__, e))
                        raise

        def execute_update(self, src, dest):
                """ handle action updates"""
                self.__executed = True
                try:
                        dest.install(self, src)
                except (pkg.actions.ActionError, EnvironmentError):
                        # Don't log these as they're expected, and should be
                        # handled by the caller.
                        raise
                except Exception, e:
                        logger.error("Action upgrade failed for '%s' (%s):\n "
                            "%s: %s" % (dest.attrs.get(dest.key_attr, id(dest)),
                             self.destination_fmri.get_pkg_stem(),
                             e.__class__.__name__, e))
                        raise

        def execute_removal(self, src, dest):
                """ handle action removals"""
                self.__executed = True
                try:
                        src.remove(self)
                except (pkg.actions.ActionError, EnvironmentError):
                        # Don't log these as they're expected, and should be
                        # handled by the caller.
                        raise
                except Exception, e:
                        logger.error("Action removal failed for '%s' (%s):\n "
                            "%s: %s" % (src.attrs.get(src.key_attr, id(src)),
                             self.origin_fmri.get_pkg_stem(),
                             e.__class__.__name__, e))
                        raise

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

                assert self.__executed
                spath = self.image.salvage(path)
                # get just the file path that was salvaged 
                fpath = path[len(self.image.get_root()) + 1:]
                self.image.imageplan.salvaged.append((fpath, spath))

        def salvage_from(self, local_path, full_destination):
                """move unpackaged contents to specified destination"""
                # remove leading / if present
                if local_path.startswith(os.path.sep):
                        local_path = local_path[1:]

                for fpath, spath in self.image.imageplan.salvaged[:]:
                        if fpath.startswith(local_path):
                                self.image.imageplan.salvaged.remove((fpath, spath))
                                break
                else:
                        return

                self.image.recover(spath, full_destination)
