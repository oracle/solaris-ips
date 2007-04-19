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

import exceptions
import re
from version import Version, DotSequence

class PkgFmri(object):
        """The authority is a short form for fetching packages from off the
        default repository search path."""

        def __init__(self, fmri, build_release):
                """XXX pkg:/?pkg_name@version not presently supported."""
                m = re.match("pkg://([^/]*)/([^@]*)@([\d\,\.]*)", fmri)
                if m != None:
                        self.authority = m.group(1)
                        self.pkg_name = m.group(2)
                        self.version = Version(m.group(3), build_release)

                        return

                m = re.match("pkg://([^/]*)/([^@]*)", fmri)
                if m != None:
                        self.authority = m.group(1)
                        self.pkg_name = m.group(2)
                        self.version = None

                        return

                m = re.match("([^@]*)@([\d\,\.]*)", fmri)
                if m != None:
                        self.authority = "localhost"
                        self.pkg_name = m.group(1)
                        self.version = Version(m.group(2), build_release)

                        return

                m = re.match("([^@]*)", fmri)
                if m != None:
                        self.authority = "localhost"
                        self.pkg_name = m.group(1)
                        self.version = None

                        return

        def __str__(self):
                if self.version == None:
                        return "pkg://%s/%s" % (self.authority, self.pkg_name)
                return "pkg://%s/%s@%s" % (self.authority, self.pkg_name,
                                self.version)

if __name__ == "__main__":
        n1 = PkgFmri("pkg://pion/sunos/coreutils", "5.9")
        n2 = PkgFmri("sunos/coreutils", "5.10")
        n3 = PkgFmri("sunos/coreutils@5.10", "5.10")

        print n1
        print n2
        print n3

