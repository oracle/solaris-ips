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
import errno
import os.path
import pkg.fmri as fmri
import pkg.misc as misc
import pkg.client.api_errors as api_errors
import pkg.client.variant as variant
from pkg.misc import msg
import pkg.portable as portable

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


# The default_policies dictionary defines the policies that are supported by 
# pkg(5) and their default values. Calls to the ImageConfig.get_policy method
# should use the constants defined here.
REQUIRE_OPTIONAL = "require-optional"
PURSUE_LATEST = "pursue-latest"
DISPLAY_COPYRIGHTS = "display-copyrights"
FLUSH_CONTENT_CACHE = "flush-content-cache-on-success"
SEND_UUID = "send-uuid"
default_policies = { 
    REQUIRE_OPTIONAL: False,
    PURSUE_LATEST: True,
    DISPLAY_COPYRIGHTS: True,
    FLUSH_CONTENT_CACHE: False,
    SEND_UUID: False,
}

# names of image configuration files managed by this module
CFG_FILE = "cfg_cache"
DA_FILE = "disabled_auth"

class ImageConfig(object):
        """An ImageConfig object is a collection of configuration information:
        URLs, authorities, properties, etc. that allow an Image to operate."""

        # XXX The SSL ssl_key attribute asserts that there is one
        # ssl_key per authority.  This may be insufficiently general:  we
        # may need one ssl_key per mirror.

        # XXX Use of ConfigParser is convenient and at most speculative--and
        # definitely not interface.

        def __init__(self):
                self.authorities = {}
                self.authority_status = {}
                self.mirror_status = {}
                self.properties = dict((
                    (p, str(v)) 
                    for p, v in default_policies.iteritems()
                ))
                self.preferred_authority = None
                self.filters = {}
                self.variants = variant.Variants()
                self.children = []

        def __str__(self):
                return "%s\n%s" % (self.authorities, self.properties)

        def get_policy(self, policy):
                """Return a boolean value for the named policy.  Returns
                the default value for the policy if the named policy is 
                not defined in the image configuration.
                """
                assert policy in default_policies
                if policy in self.properties:
                        policystr = self.properties[policy]
                        return policystr.lower() in ("true", "yes")
                return default_policies[policy]
                
        def read(self, dir):
                """Read the config files for the image from the given directory."""

                cp = ConfigParser.SafeConfigParser()

                ccfile = os.path.join(dir, CFG_FILE)
                r = cp.read(ccfile)
                if len(r) == 0:
                        raise RuntimeError("Couldn't read configuration from %s" % ccfile)

                assert r[0] == ccfile

                for s in cp.sections():
                        if re.match("authority_.*", s):
                                k, a = self.read_authority(cp, s)
                                ms = []

                                self.authorities[k] = a
                                self.authority_status[k] = DepotStatus(k,
                                    a["origin"])

                                for mirror in a["mirrors"]:
                                        ms.append(DepotStatus(k, mirror))

                                self.mirror_status[k] = ms
                                
                                if self.preferred_authority == None:
                                        self.preferred_authority = k

                # read in the policy section to provide backward
                # compatibility for older images
                if cp.has_section("policy"):
                        for o in cp.options("policy"):
                                self.properties[o] = cp.get("policy", o)

                if cp.has_section("property"):
                        for o in cp.options("property"):
                                self.properties[o] = cp.get("property", 
                                    o, raw=True).decode('utf-8')

                if cp.has_section("filter"):
                        for o in cp.options("filter"):
                                self.filters[o] = cp.get("filter", o)

                if cp.has_section("variant"):
                        for o in cp.options("variant"):
                                self.variants[o] = cp.get("variant", o)

                if "preferred-authority" in self.properties:
                        self.preferred_authority = self.properties["preferred-authority"]

                # read disabled authority file
                # XXX when compatility with the old code is no longer needed,
                # this can be removed
                cp = ConfigParser.SafeConfigParser()
                dafile = os.path.join(dir, DA_FILE)
                if os.path.exists(dafile):
                        r = cp.read(dafile)
                        if len(r) == 0:
                                raise RuntimeError("Couldn't read configuration from %s" % dafile)
                        for s in cp.sections():
                                if re.match("authority_.*", s):
                                        k, a = self.read_authority(cp, s)
                                        self.authorities[k] = a
                                        # status objects are not created for
                                        # disabled authorities

        def write(self, dir):
                """Write the configuration to the given directory"""
                cp = ConfigParser.SafeConfigParser()
                # XXX the use of the disabled_auth file can be removed when
                # compatibility with the older code is no longer needed
                da = ConfigParser.SafeConfigParser()
                self.properties["preferred-authority"] = self.preferred_authority

                cp.add_section("property")
                for p in self.properties:
                        cp.set("property", p, self.properties[p].encode('utf-8'))

                cp.add_section("filter")
                for f in self.filters:
                        cp.set("filter", f, str(self.filters[f]))

                cp.add_section("variant")
                for f in self.variants:
                        cp.set("variant", f, str(self.variants[f]))

                for a in self.authorities:
                        auth = self.authorities[a]
                        section = "authority_%s" % auth["prefix"]

                        c = cp
                        if auth["disabled"]:
                                c = da

                        c.add_section(section)
                        c.set(section, "prefix", auth["prefix"])
                        c.set(section, "origin", auth["origin"])
                        c.set(section, "disabled", str(auth["disabled"]))
                        c.set(section, "mirrors", str(auth["mirrors"]))
                        c.set(section, "ssl_key", str(auth["ssl_key"]))
                        c.set(section, "ssl_cert", str(auth["ssl_cert"]))
                        c.set(section, "uuid", str(auth["uuid"]))

                # XXX Child images

                for afile, acp in [(CFG_FILE, cp), (DA_FILE, da)]:
                        thefile = os.path.join(dir, afile)
                        if len(acp.sections()) == 0:
                                if os.path.exists(thefile):
                                        portable.remove(thefile)
                                continue
                        try:
                                f = open(thefile, "w")
                        except EnvironmentError, e:
                                if e.errno == errno.EACCES:
                                        raise api_errors.PermissionsException(
                                            e.filename)
                                raise
                        acp.write(f)

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

        def read_authority(self, cp, s):
                # authority block has prefix, origin, and mirrors
                a = {}
                k = cp.get(s, "prefix")

                if k.startswith(fmri.PREF_AUTH_PFX):
                        raise RuntimeError(
                            "Invalid Authority name: %s" % k)

                a["prefix"] = k
                a["origin"] = cp.get(s, "origin")
                try:
                        d = cp.get(s, "disabled")
                except ConfigParser.NoOptionError:
                        d = 'False'
                a["disabled"] = d.lower() in ("true", "yes")

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

                try:
                        a["uuid"] = cp.get(s, "uuid")
                except ConfigParser.NoOptionError:
                        a["uuid"] = "None"

                a["origin"] = \
                    misc.url_affix_trailing_slash(a["origin"])

                return k, a
