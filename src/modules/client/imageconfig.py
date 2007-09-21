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

# Copyright 2007 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import ConfigParser
import re

class ImageConfig(object):
        """An ImageConfig object is a collection of configuration information:
        URLs, authorities, policies, etc. that allow an Image to operate."""

        # XXX Use of ConfigParser is convenient and at most speculative--and
        # definitely not interface.

        def __init__(self):
                self.authorities = {}
                self.preferred_authority = None
                self.filters = {}

                self.children = []

                self.policies = {}
                self.policies["require-optional"] = False
                self.policies["pursue-latest"] = True
                self.policies["display-copyrights"] = True

        def __str__(self):
                return "%s\n%s" % (self.authorities, self.policies)

        def read(self, path):
                """Read the given file as if it were a configuration cache for
                pkg(1)."""

                cp = ConfigParser.SafeConfigParser()

                r = cp.read(path)
                if r[0] != path:
                        raise ParseError

                for s in cp.sections():
                        if re.match("authority_.*", s):
                                # authority block has prefix, origin, and
                                # mirrors
                                a = {}

                                k = a["prefix"] = cp.get(s, "prefix")
                                a["origin"] = cp.get(s, "origin")
                                a["mirrors"] = cp.get(s, "mirrors")

                                self.authorities[k] = a

                                if self.preferred_authority == None:
                                        self.preferred_authority = k

                        if re.match("policy", s):
                                for o in cp.options("policy"):
                                        self.policies[o] = cp.get("policy", o)

                        if re.match("filter", s):
                                for o in cp.options("filter"):
                                        self.filters[o] = cp.get("filter", o)

                        # XXX Child images

                if "preferred-authority" in self.policies:
                        self.preferred_authority = self.policies["preferred-authority"]


        def write(self, path):
                cp = ConfigParser.SafeConfigParser()

                self.policies["preferred-authority"] = self.preferred_authority

                cp.add_section("policy")
                for p in self.policies:
                        cp.set("policy", p, str(self.policies[p]))

                cp.add_section("filter")
                for f in self.filters:
                        cp.set("filter", f, str(self.filters[f]))

                for a in self.authorities:
                        section = "authority_%s" % self.authorities[a]["prefix"]

                        cp.add_section(section)

                        cp.set(section, "prefix",
                            self.authorities[a]["prefix"])
                        cp.set(section, "origin",
                            self.authorities[a]["origin"])
                        cp.set(section, "mirrors",
                            str(self.authorities[a]["mirrors"]))

                # XXX Child images

                f = open(path, "w")
                cp.write(f)

if __name__ == "__main__":
        # XXX Need to construct a trivial configuration, load it, and verify
        # correctness.
        ic = ImageConfig()
        ic.read("tests/sampleconfig.conf")

        print ic
