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
# Copyright 2007 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

"""module describing a file packaging object

This module contains the FileAction class, which represents a file-type
packaging object."""

import generic

class FileAction(generic.Action):
        """Class representing a file-type packaging object."""

        def __init__(self, data=None, **attrs):
                generic.Action.__init__(self, data, **attrs)

        def preinstall(self):
                """Client-side method that performs pre-install actions."""
                pass

        def install(self):
                """Client-side method that installs a file."""
                pass

        def postinstall(self):
                """Client-side method that performs post-install actions."""
                pass

        @staticmethod
        def attributes():
                """Returns the tuple of attributes required for files."""
                return ("mode", "owner", "group", "path")

        @staticmethod
        def name():
                """Returns the name of the action."""
                return "file"
