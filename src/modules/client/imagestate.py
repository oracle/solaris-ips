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

# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
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

        def __init__(self):
                self.__fmri_intent_stack = []

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

