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

import ConfigParser
import re
import pkg.fmri as fmri
import pkg.misc as misc
from pkg.misc import msg

class DepotStatus(object):
        """An object that encapsulates status about a depot server.
        This includes things like observed performance, availability,
        successful and unsuccessful transaction rates, etc."""

        def __init__(self, authority, url):
                """Authority is the authority prefix for this depot.
                Url is the URL that names the server or mirror itself."""

                self.auth = authority
                self.url = url.rstrip("/")
                self.available = True

                self.errors = 0
                self.good_tx = 0

                self.last_tx_time = None

        def record_error(self):

                self.errors += 1

        def record_success(self, tx_time):

                self.good_tx += 1
                self.last_tx_time = tx_time

        def set_available(self, avail):

                if avail:
                        self.available = True
                else:
                        self.available = False


class ImageConfig(object):
        """An ImageConfig object is a collection of configuration information:
        URLs, authorities, policies, etc. that allow an Image to operate."""

        # XXX The SSL ssl_key attribute asserts that there is one
        # ssl_key per authority.  This may be insufficiently general:  we
        # may need one ssl_key per mirror.

        # XXX Use of ConfigParser is convenient and at most speculative--and
        # definitely not interface.

        BOOLEAN_POLICIES = [
                "require-optional",
                "pursue-latest",
                "display-copyrights",
                "flush-content-cache-on-success" ]       

        def __init__(self):
                self.authorities = {}
                self.authority_status = {}
                self.mirror_status = {}
                self.preferred_authority = None
                self.flush_content_cache = False
                self.filters = {}

                self.children = []

                self.policies = {}
                self.policies["require-optional"] = False
                self.policies["pursue-latest"] = True
                self.policies["display-copyrights"] = True
                self.policies["flush-content-cache-on-success"] = False

        def __str__(self):
                return "%s\n%s" % (self.authorities, self.policies)

        def read(self, path):
                """Read the given file as if it were a configuration cache for
                pkg(1)."""

                cp = ConfigParser.SafeConfigParser()

                r = cp.read(path)
                if len(r) == 0:
                        raise RuntimeError("Couldn't read configuration %s" % path)

                assert r[0] == path

                for s in cp.sections():
                        if re.match("authority_.*", s):
                                # authority block has prefix, origin, and
                                # mirrors
                                a = {}
                                ms = []

                                k = cp.get(s, "prefix")

                                if k.startswith(fmri.PREF_AUTH_PFX):
                                        raise RuntimeError(
                                            "Invalid Authority name: %s" % k)

                                a["prefix"] = k
                                a["origin"] = cp.get(s, "origin")
                                mir_str = cp.get(s, "mirrors")
                                if mir_str == "None":
                                        a["mirrors"] = []
                                else:
                                        a["mirrors"] = self.read_list(mir_str)

                                try:
                                        a["ssl_key"] = cp.get(s, "ssl_key")
                                        if a["ssl_key"] == "None":
                                                a["ssl_key"] = None
                                except ConfigParser.NoOptionError:
                                        a["ssl_key"] = None

                                try:
                                        a["ssl_cert"] = cp.get(s, "ssl_cert")
                                        if a["ssl_cert"] == "None":
                                                a["ssl_cert"] = None
                                except ConfigParser.NoOptionError:
                                        a["ssl_cert"] = None

                                a["origin"] = \
                                    misc.url_affix_trailing_slash(a["origin"])

                                self.authorities[k] = a
                                self.authority_status[k] = DepotStatus(k,
                                    a["origin"])

                                for mirror in a["mirrors"]:
                                        ms.append(DepotStatus(k, mirror))
                                ms.append(self.authority_status[k])

                                self.mirror_status[k] = ms
                                
                                if self.preferred_authority == None:
                                        self.preferred_authority = k

                if cp.has_section("policy"):
                        for o in cp.options("policy"):
                                if o in self.BOOLEAN_POLICIES:
                                        self.policies[o] = \
                                            cp.getboolean("policy", o)
                                else:
                                        self.policies[o] = cp.get("policy", o)

                if cp.has_section("filter"):
                        for o in cp.options("filter"):
                                self.filters[o] = cp.get("filter", o)

                if "preferred-authority" in self.policies:
                        self.preferred_authority = \
                            self.policies["preferred-authority"]

                if "flush-content-cache-on-success" in self.policies:
                        self.flush_content_cache = \
                            self.policies["flush-content-cache-on-success"]

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
                        cp.set(section, "ssl_key",
                            str(self.authorities[a]["ssl_key"]))
                        cp.set(section, "ssl_cert",
                            str(self.authorities[a]["ssl_cert"]))

                # XXX Child images

                try:
                        f = open(path, "w")
                except IOError, (errno, strerror):
                        raise RuntimeError("unable to open %s for writing: %s" %
                                (path, strerror))
                cp.write(f)

        def delete_authority(self, auth):
                del self.authorities[auth]

        @staticmethod
        def read_list(str):
                """Take a list in string representation and convert it back
                to a Python list."""
                
                # Strip brackets and any whitespace
                str = str.strip("][ ")
                # Strip comma and any whitespeace
                lst = str.split(", ")
                # Strip empty whitespace, single, and double quotation marks
                lst = [ s.strip("' \"") for s in lst ]
                # Eliminate any empty strings
                lst = [ s for s in lst if s != '' ]

                return lst
