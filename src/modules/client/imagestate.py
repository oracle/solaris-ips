#!/usr/bin/python2.4
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

# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

# Indicates that the fmri is being used strictly for information.
INTENT_INFO = "info"

# Indicates that the fmri is being used to perform a dry-run evaluation of an
# image-modifying operation.
INTENT_EVALUATE = "evaluate"

# Indicates that the fmri is being processed as part of an image-modifying
# operation.
INTENT_PROCESS = "process"

class ImageState(object):
        """An ImageState object provides a temporary place to store information
        about operations that are being performed on an image (e.g. fmris of
        packages that are being installed, uninstalled, etc.).
        """

        def __init__(self, image):
                self.__fmri_intent_stack = []
                self.__image = image

                # A place to keep track of which manifests (based on fmri and
                # operation) have already provided intent information.
                self.__touched_manifests = {}

        def __str__(self):
                return "%s" % self.__fmri_intent_stack

        def set_target(self, fmri=None, intent=INTENT_INFO):
                """Indicates that the given fmri is currently being evaluated
                or manipulated for an image operation.  A value of None for
                fmri will clear the current target.
                """
                if fmri:
                        self.__fmri_intent_stack.append((fmri, intent))
                else:
                        del self.__fmri_intent_stack[-1]

        def get_target(self):
                """Returns a tuple of the format (fmri, intent) representing an
                fmri currently being evaluated or manipulated for an image
                operation.  A tuple containing (None, None) will be returned if
                no target has been set.
                """
                try:
                        return self.__fmri_intent_stack[-1]
                except IndexError:
                        return (None, None)

        def get_targets(self):
                """Returns a list of tuples of the format (fmri, intent)
                representing fmris currently being evaluated or manipulated for
                an image operation.  An empty list is returned if there are no
                targets.
                """
                return self.__fmri_intent_stack[:]

        def get_touched_manifest(self, fmri, intent):
                """Returns whether intent information has been provided for the
                given fmri."""

                op = self.__image.history.operation_name
                if not op:
                        # The client may not have provided the name of the
                        # operation it is performing.
                        op = "unknown"

                if op not in self.__touched_manifests:
                        # No intent information has been provided for fmris
                        # for the current operation.
                        return False

                f = str(fmri)
                if f not in self.__touched_manifests[op]:
                        # No intent information has been provided for this
                        # fmri for the current operation.
                        return False

                if intent not in self.__touched_manifests[op][f]:
                        # No intent information has been provided for this
                        # fmri for the current operation and reason.
                        return False

                return True

        def set_touched_manifest(self, fmri, intent):
                """Records that intent information has been provided for the
                given fmri's manifest."""

                op = self.__image.history.operation_name
                if not op:
                        # The client may not have provided the name of the
                        # operation it is performing.
                        op = "unknown"

                if op not in self.__touched_manifests:
                        # No intent information has yet been provided for fmris
                        # for the current operation.
                        self.__touched_manifests[op] = {}

                f = str(fmri)
                if f not in self.__touched_manifests[op]:
                        # No intent information has yet been provided for this
                        # fmri for the current operation.
                        self.__touched_manifests[op][f] = { intent: None }
                else:
                        # No intent information has yet been provided for this
                        # fmri for the current operation and reason.
                        self.__touched_manifests[op][f][intent] = None

        def get_intent_str(self, fmri):
                """Returns a string representing the intent of the client
                in retrieving information based on the operation information
                provided by the image history object.
                """

                op = self.__image.history.operation_name
                if not op:
                        # The client hasn't indicated what operation
                        # is executing.
                        op = "unknown"

                reason = INTENT_INFO
                target_pkg = None
                initial_pkg = None
                needed_by_pkg = None
                current_pub = fmri.get_publisher()

                targets = self.get_targets()
                if targets:
                        # Attempt to determine why the client is retrieving the
                        # manifest for this fmri and what its current target is.
                        target, reason = targets[-1]

                        # Compare the FMRIs with no publisher information
                        # embedded.
                        na_current = fmri.get_fmri(anarchy=True)
                        na_target = target.get_fmri(anarchy=True)

                        if na_target == na_current:
                                # Only provide this information if the fmri for
                                # the manifest being retrieved matches the fmri
                                # of the target.  If they do not match, then the
                                # target fmri is being retrieved for information
                                # purposes only (e.g.  dependency calculation,
                                # etc.).
                                target_pub = target.get_publisher()
                                if target_pub == current_pub:
                                        # Prevent providing information across
                                        # publishers.
                                        target_pkg = na_target[len("pkg:/"):]
                                else:
                                        target_pkg = "unknown"

                                # The very first fmri should be the initial
                                # target that caused the current and needed_by
                                # fmris to be retrieved.
                                initial = targets[0][0]
                                initial_pub = initial.get_publisher()
                                if initial_pub == current_pub:
                                        # Prevent providing information across
                                        # publishers.
                                        initial_pkg = initial.get_fmri(
                                            anarchy=True)[len("pkg:/"):]

                                        if target_pkg == initial_pkg:
                                                # Don't bother sending the
                                                # target information if it is
                                                # the same as the initial target
                                                # (i.e. the manifest for foo@1.0
                                                # is being retrieved because the
                                                # user is installing foo@1.0).
                                                target_pkg = None

                                else:
                                        # If they didn't match, indicate that
                                        # the needed_by_pkg was a dependency of
                                        # another, but not which one.
                                        initial_pkg = "unknown"

                                if len(targets) > 1:
                                        # The fmri responsible for the current
                                        # one being processed should immediately
                                        # precede the current one in the target
                                        # list.
                                        needed_by = targets[-2][0]

                                        needed_by_pub = \
                                            needed_by.get_publisher()
                                        if needed_by_pub == current_pub:
                                                # To prevent dependency
                                                # information being shared
                                                # across publisher boundaries,
                                                # publishers must match.
                                                needed_by_pkg = \
                                                    needed_by.get_fmri(
                                                    anarchy=True)[len("pkg:/"):]
                                        else:
                                                # If they didn't match, indicate
                                                # that the package is needed by
                                                # another, but not which one.
                                                needed_by_pkg = "unknown"
                else:
                        # An operation is being performed that has not provided
                        # any target information and is likely for informational
                        # purposes only.  Assume the "initial target" is what is
                        # being retrieved.
                        initial_pkg = str(fmri)[len("pkg:/"):]

                prior_version = None
                if reason != INTENT_INFO:
                        # Only provide version information for non-informational
                        # operations.
                        prior = self.__image.get_version_installed(fmri)

                        try:
                                prior_version = prior.version
                        except AttributeError:
                                # We didn't get a match back, drive on.
                                pass
                        else:
                                prior_pub = prior.get_publisher()
                                if prior_pub != current_pub:
                                        # Prevent providing information across
                                        # publishers by indicating that a prior
                                        # version was installed, but not which
                                        # one.
                                        prior_version = "unknown"

                info = {
                    "operation": op,
                    "prior_version": prior_version,
                    "reason": reason,
                    "target": target_pkg,
                    "initial_target": initial_pkg,
                    "needed_by": needed_by_pkg,
                }

                # op/prior_version/reason/initial_target/needed_by/
                return "(%s)" % ";".join([
                    "%s=%s" % (key, info[key]) for key in info
                    if info[key] is not None
                ])
