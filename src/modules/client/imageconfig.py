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
# Copyright (c) 2007, 2010 Oracle and/or its affiliates.  All rights reserved.
#

import ConfigParser
import errno
import os.path
import platform
import re

from pkg.client import global_settings
logger = global_settings.logger

import pkg.client.api_errors  as api_errors
import pkg.client.publisher   as publisher
import pkg.facet              as facet
import pkg.fmri               as fmri
import pkg.portable           as portable
import pkg.client.sigpolicy   as sigpolicy
import pkg.variant            as variant

from pkg.misc import DictProperty, SIGNATURE_POLICY
# The default_policies dictionary defines the policies that are supported by
# pkg(5) and their default values. Calls to the ImageConfig.get_policy method
# should use the constants defined here.

FLUSH_CONTENT_CACHE = "flush-content-cache-on-success"
MIRROR_DISCOVERY = "mirror-discovery"
SEND_UUID = "send-uuid"

default_policies = {
    FLUSH_CONTENT_CACHE: False,
    MIRROR_DISCOVERY: False,
    SEND_UUID: True,
    SIGNATURE_POLICY: sigpolicy.DEFAULT_POLICY
}

CA_PATH = "ca-path"
# Default CA_PATH is /etc/openssl/certs
default_properties = {
        CA_PATH: os.path.join(os.path.sep, "etc", "openssl", "certs")
}

# Assume the repository metadata should be checked no more than once every
# 4 hours.
REPO_REFRESH_SECONDS_DEFAULT = 4 * 60 * 60

# names of image configuration files managed by this module
CFG_FILE = "cfg_cache"
DA_FILE = "disabled_auth"


class ImageConfig(object):
        """An ImageConfig object is a collection of configuration information:
        URLs, publishers, properties, etc. that allow an Image to operate."""

        # XXX The SSL ssl_key attribute asserts that there is one
        # ssl_key per publisher.  This may be insufficiently general:  we
        # may need one ssl_key per mirror.

        # XXX Use of ConfigParser is convenient and at most speculative--and
        # definitely not interface.

        def __init__(self, imgroot, pubdir):
                self.__imgroot = imgroot
                self.__pubdir = pubdir
                self.__publishers = {}
                self.__publisher_search_order = []

                self.__properties = dict((
                    (p, str(v))
                    for p, v in default_policies.iteritems()
                ))
                self.properties.update(dict((
                    (p, str(v))
                    for p, v in default_properties.iteritems()
                )))
                self.facets = facet.Facets()
                self.variants = variant.Variants()
                self.children = []
                self.__delay_validation = False

        def __str__(self):
                return "%s\n%s" % (self.__publishers, self.properties)

        def __get_preferred_publisher(self):
                """Returns prefix of preferred publisher"""

                for p in self.__publisher_search_order:
                        if not self.__publishers[p].disabled:
                                return p
                raise KeyError, "No preferred publisher"

        def __set_preferred_publisher(self, prefix):
                """Enforce search order rules"""
                if prefix not in self.__publishers:
                        raise KeyError, "Publisher %s not found" % prefix
                self.__publisher_search_order.remove(prefix)
                self.__publisher_search_order.insert(0, prefix)

        def remove_publisher(self, prefix):
                """External functional interface - use property interface"""
                del self.publishers[prefix]

        def change_publisher_search_order(self, new_world_order):
                """Change search order to desired value"""
                if sorted(new_world_order) != sorted(self.__publisher_search_order):
                        raise ValueError, "publishers added or removed"
                self.__publisher_search_order = new_world_order

        def __get_publisher(self, prefix):
                """Accessor method for publishers dictionary"""
                return self.__publishers[prefix]

        def __set_publisher(self, prefix, value):
                """Accesor method to keep search order correct on insert"""
                if prefix not in self.__publisher_search_order:
                        self.__publisher_search_order.append(prefix)
                self.__publishers[prefix] = value

        def __del_publisher(self, prefix):
                """Accessor method for publishers"""
                if prefix in self.__publisher_search_order:
                        self.__publisher_search_order.remove(prefix)
                del self.__publishers[prefix]

        def __publisher_iter(self):
                return self.__publishers.__iter__()

        def __publisher_iteritems(self):
                """Support iteritems on publishers"""
                return self.__publishers.iteritems()

        def __publisher_keys(self):
                """Support keys() on publishers"""
                return self.__publishers.keys()

        def __publisher_values(self):
                """Support values() on publishers"""
                return self.__publishers.values()

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

        def get_policy_str(self, policy):
                """Return a boolean value for the named policy.  Returns
                the default value for the policy if the named policy is
                not defined in the image configuration.
                """
                assert policy in default_policies
                return self.__properties.get(policy, default_policies[policy])

        def read(self, path):
                """Read the config files for the image from the given directory.
                """
                # keep track of whether the config needs to be rewritten
                changed = False

                cp = ConfigParser.SafeConfigParser()
                cp.optionxform = str # preserve option case

                ccfile = os.path.join(path, CFG_FILE)
                r = cp.read(ccfile)
                if len(r) == 0:
                        raise RuntimeError("Couldn't read configuration from "
                            "%s" % ccfile)

                assert r[0] == ccfile

                # The root directory for publisher metadata.
                pmroot = os.path.join(path, self.__pubdir)

                #
                # Must load filters first, since the value of a filter can
                # impact the default value of the zone variant.  This is
                # legacy code, and should be removed when upgrade from
                # pre-variant versions of opensolaris is no longer
                # supported
                #

                filters = {}
                if cp.has_section("filter"):
                        for o in cp.options("filter"):
                                filters[o] = cp.get("filter", o)

                #
                # Must load variants next, since in the case of zones,
                # the variant can impact the processing of publishers.
                #
                if cp.has_section("variant"):
                        for o in cp.options("variant"):
                                self.variants[o] = cp.get("variant", o)
                # facets
                if cp.has_section("facet"):
                        for o in cp.options("facet"):
                                self.facets[o] = cp.get("facet", o) != "False"
                # make sure we define architecture variant
                if "variant.arch" not in self.variants:
                        self.variants["variant.arch"] = platform.processor()
                        changed = True

                # make sure we define zone variant
                if "variant.opensolaris.zone" not in self.variants:
                        zone = filters.get("opensolaris.zone", "")
                        if zone == "nonglobal":
                                self.variants[
                                    "variant.opensolaris.zone"] = "nonglobal"
                        else:
                                self.variants[
                                    "variant.opensolaris.zone"] = "global"
                        changed = True

                preferred_publisher = None
                for s in cp.sections():
                        if re.match("authority_.*", s):
                                k, a, c = self.read_publisher(pmroot, cp, s)
                                changed |= c
                                self.publishers[k] = a
                                # just in case there's no other indication
                                if preferred_publisher is None:
                                        preferred_publisher = k

                # read in the policy section to provide backward
                # compatibility for older images
                if cp.has_section("policy"):
                        for o in cp.options("policy"):
                                self.properties[o] = cp.get("policy", o)

                # Set __delay_validation to be True so that the order the
                # properties are read doesn't matter.
                self.__delay_validation = True
                if cp.has_section("property"):
                        for o in cp.options("property"):
                                self.properties[o] = cp.get("property",
                                    o, raw=True).decode('utf-8')
                self.__delay_validation = False
                # Now validate the properties are consistent.
                self.__validate_properties()

                try:
                        preferred_publisher = \
                            str(self.properties["preferred-publisher"])
                except KeyError:
                        try:
                                # Compatibility with older clients.
                                self.properties["preferred-publisher"] = \
                                    str(self.properties["preferred-authority"])
                                preferred_publisher = \
                                    self.properties["preferred-publisher"]
                                del self.properties["preferred-authority"]
                        except KeyError:
                                pass

                try:
                        self.properties["ca-path"] = str(
                            self.properties["ca-path"])
                except KeyError:
                        self.properties["ca-path"] = \
                            self.default_properties["ca-path"]

                # read disabled publisher file
                # XXX when compatility with the old code is no longer needed,
                # this can be removed
                cp = ConfigParser.SafeConfigParser()
                dafile = os.path.join(path, DA_FILE)
                if os.path.exists(dafile):
                        r = cp.read(dafile)
                        if len(r) == 0:
                                raise RuntimeError("Couldn't read "
                                    "configuration from %s" % dafile)
                        for s in cp.sections():
                                if re.match("authority_.*", s):
                                        k, a, c = self.read_publisher(pmroot,
                                            cp, s)
                                        self.publishers[k] = a
                                        changed |= c

                try:
                        self.__publisher_search_order = self.read_list(
                            str(self.properties["publisher-search-order"]))
                except KeyError:
                        # make up the default - preferred, then the rest in
                        # alpha order
                        self.__publisher_search_order = [preferred_publisher] + \
                            sorted([ 
                                name 
                                for name in self.__publishers.keys() 
                                if name != preferred_publisher
                                ])
                        changed = True
                else:
                        # Ensure that all configured publishers are present in
                        # search order (add them in alpha order to the end).
                        # Also ensure that all publishers in search order that
                        # are not known are removed.
                        known_pubs = set(self.__publishers.keys())
                        sorted_pubs = set(self.__publisher_search_order)
                        new_pubs = known_pubs - sorted_pubs
                        old_pubs = sorted_pubs - known_pubs

                        for pub in old_pubs:
                                self.__publisher_search_order.remove(pub)

                        self.__publisher_search_order.extend(sorted(new_pubs))
                        
                self.properties["publisher-search-order"] = \
                    str(self.__publisher_search_order)

                # If the configuration changed, rewrite it if possible.
                if changed:
                        try:
                                self.write(path)
                        except api_errors.PermissionsException:
                                pass

        def write(self, path):
                """Write the configuration to the given directory"""
                cp = ConfigParser.SafeConfigParser()
                # XXX the use of the disabled_auth file can be removed when
                # compatibility with the older code is no longer needed
                da = ConfigParser.SafeConfigParser()
                cp.optionxform = str # preserve option case

                # For compatibility, the preferred-publisher is written out
                # as the preferred-authority.  Modify a copy so that we don't
                # change the in-memory copy.
                props = self.__properties.copy()
                try:
                        del props["preferred-publisher"]
                except KeyError:
                        pass
                props["preferred-authority"] = str(self.__publisher_search_order[0])
                props["publisher-search-order"] = str(self.__publisher_search_order)

                cp.add_section("property")
                for p in props:
                        if isinstance(props[p], basestring):
                                cp.set("property", p, props[p].encode("utf-8"))
                        else:
                                cp.set("property", p, str(props[p]).encode(
                                    "utf-8"))

                cp.add_section("variant")
                for f in self.variants:
                        cp.set("variant", f, str(self.variants[f]))

                cp.add_section("facet")

                for f in self.facets:

                        cp.set("facet", f, str(self.facets[f]))

                for prefix in self.__publishers:
                        pub = self.__publishers[prefix]
                        section = "authority_%s" % pub.prefix

                        c = cp
                        if pub.disabled:
                                c = da

                        c.add_section(section)
                        c.set(section, "alias", str(pub.alias))
                        c.set(section, "prefix", str(pub.prefix))
                        c.set(section, "signing_ca_certs", str(
                            pub.signing_ca_certs))
                        c.set(section, "approved_ca_certs", str(
                            pub.approved_ca_certs))
                        c.set(section, "revoked_ca_certs", str(
                            pub.revoked_ca_certs))
                        c.set(section, "intermediate_certs", str(
                            pub.inter_certs))
                        c.set(section, "disabled", str(pub.disabled))
                        c.set(section, "sticky", str(pub.sticky))

                        repo = pub.selected_repository

                        # For now, write out "origin" for compatibility with
                        # older clients in addition to "origins".  Older
                        # clients may drop the "origins" when rewriting the
                        # configuration, but that doesn't really break
                        # anything.
                        c.set(section, "origin", repo.origins[0].uri)

                        c.set(section, "origins",
                            str([u.uri for u in repo.origins]))
                        c.set(section, "mirrors",
                            str([u.uri for u in repo.mirrors]))

                        if repo.system_repo:
                                c.set(section, "sysrepo.uri",
                                    str(repo.system_repo))
                                c.set(section, "sysrepo.sock_path",
                                    repo.system_repo.socket_path)
                        else:
                                c.set(section, "sysrepo.uri", "None")
                                c.set(section, "sysrepo.sock_path", "None")

                        #
                        # For zones, where the reachability of an absolute path
                        # changes depending on whether you're in the zone or
                        # not.  So we have a different policy: ssl_key and
                        # ssl_cert are treated as zone root relative.
                        #
                        ngz = self.variants.get("variant.opensolaris.zone",
                            "global") == "nonglobal"
                        p = str(pub["ssl_key"])
                        if ngz and self.__imgroot != os.sep and p != "None":
                                # Trim the imageroot from the path.
                                if p.startswith(self.__imgroot):
                                        p = p[len(self.__imgroot):]
                        # XXX this should be per origin or mirror
                        c.set(section, "ssl_key", p)
                        p = str(pub["ssl_cert"])
                        if ngz and self.__imgroot != os.sep and p != "None":
                                if p.startswith(self.__imgroot):
                                        p = p[len(self.__imgroot):]
                        # XXX this should be per origin or mirror
                        c.set(section, "ssl_cert", p)

                        # XXX this should really be client_uuid, but is being
                        # left with this name for compatibility with older
                        # clients.
                        c.set(section, "uuid", str(pub.client_uuid))

                        # Write selected repository data.
                        # XXX this is temporary until a switch to a more
                        # expressive configuration format is made.
                        repo = pub.selected_repository
                        repo_data = {
                            "collection_type": repo.collection_type,
                            "description": repo.description,
                            "legal_uris": [u.uri for u in repo.legal_uris],
                            "name": repo.name,
                            "refresh_seconds": repo.refresh_seconds,
                            "registered": repo.registered,
                            "registration_uri": repo.registration_uri,
                            "related_uris": [u.uri for u in repo.related_uris],
                            "sort_policy": repo.sort_policy,
                        }

                        for key, val in repo_data.iteritems():
                                c.set(section, "repo.%s" % key, str(val))

                        for key, val in pub.properties.iteritems():
                                c.set(section, "property.%s" % key, str(val))

                # XXX Child images

                for afile, acp in [(CFG_FILE, cp), (DA_FILE, da)]:
                        thefile = os.path.join(path, afile)
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
                                if e.errno == errno.EROFS:
                                        raise api_errors.ReadOnlyFileSystemException(
                                            e.filename)
                                raise
                        acp.write(f)

        @staticmethod
        def read_list(list_str):
                """Take a list in string representation and convert it back
                to a Python list."""

                list_str = list_str.encode("utf-8")
                # Strip brackets and any whitespace
                list_str = list_str.strip("][ ")
                # Strip comma and any whitespeace
                lst = list_str.split(", ")
                # Strip empty whitespace, single, and double quotation marks
                lst = [ s.strip("' \"") for s in lst ]
                # Eliminate any empty strings
                lst = [ s for s in lst if s != '' ]

                return lst

        def read_publisher(self, meta_root, cp, s):
                # s is the section of the config file.
                # publisher block has alias, prefix, origin, and mirrors
                changed = False
                try:
                        alias = cp.get(s, "alias")
                        if alias == "None":
                                alias = None
                except ConfigParser.NoOptionError:
                        alias = None

                prefix = cp.get(s, "prefix")

                try:
                        ca_certs = self.read_list(cp.get(s, "signing_ca_certs"))
                except ConfigParser.NoOptionError:
                        ca_certs = []

                try:
                        approved_ca_certs = self.read_list(cp.get(s,
                            "approved_ca_certs"))
                except ConfigParser.NoOptionError:
                        approved_ca_certs = []

                try:
                        revoked_ca_certs = self.read_list(cp.get(s,
                            "revoked_ca_certs"))
                except ConfigParser.NoOptionError:
                        revoked_ca_certs = []

                try:
                        inter_certs = self.read_list(cp.get(s,
                            "intermediate_certs"))
                except ConfigParser.NoOptionError:
                        inter_certs = []
                try:
                        signature_policy = cp.get(s, "signature_policy")
                except ConfigParser.NoOptionError:
                        signature_policy = sigpolicy.DEFAULT_POLICY
                try:
                        signature_names = self.read_list(cp.get(s,
                            "signature-required-names"))
                except ConfigParser.NoOptionError:
                        signature_names = []

                if prefix.startswith(fmri.PREF_PUB_PFX):
                        raise RuntimeError(
                            "Invalid Publisher name: %s" % prefix)

                try:
                        sticky = cp.getboolean(s, "sticky")
                except (ConfigParser.NoOptionError, ValueError):
                        sticky = True

                try:
                        d = cp.get(s, "disabled")
                except ConfigParser.NoOptionError:
                        d = 'False'
                disabled = d.lower() in ("true", "yes")

                origin = cp.get(s, "origin")
                try:
                        sysrepo_uristr = cp.get(s, "sysrepo.uri")
                except ConfigParser.NoOptionError:
                        sysrepo_uristr = "None"
                try:
                        sysrepo_sock_path = cp.get(s, "sysrepo.sock_path")
                except ConfigParser.NoOptionError:
                        sysrepo_sock_path = "None"

                try:
                        org_str = cp.get(s, "origins")
                except ConfigParser.NoOptionError:
                        org_str = "None"

                if org_str == "None":
                        origins = []
                else:
                        origins = self.read_list(org_str)

                # Ensure that the list of origins is unique and complete.
                origins = set(origins)
                if origin != "None":
                        origins.add(origin)

                if sysrepo_uristr in origins:
                        origins.remove(sysrepo_uristr)

                mir_str = cp.get(s, "mirrors")
                if mir_str == "None":
                        mirrors = []
                else:
                        mirrors = self.read_list(mir_str)

                try:
                        ssl_key = cp.get(s, "ssl_key")
                        if ssl_key == "None":
                                ssl_key = None
                except ConfigParser.NoOptionError:
                        ssl_key = None

                try:
                        ssl_cert = cp.get(s, "ssl_cert")
                        if ssl_cert == "None":
                                ssl_cert = None
                except ConfigParser.NoOptionError:
                        ssl_cert = None

                try:
                        # XXX this should really be client_uuid, but is being
                        # left with this name for compatibility with older
                        # clients.
                        client_uuid = cp.get(s, "uuid")
                        if client_uuid == "None":
                                client_uuid = None
                except ConfigParser.NoOptionError:
                        client_uuid = None

                props = {}
                for opt in cp.options(s):
                        if not opt.startswith("property."):
                                continue
                        prop_name = opt[len("property."):]
                        val = self.read_list(cp.get(s, opt))
                        props[prop_name] = val

                # Load selected repository data.
                # XXX this is temporary until a switch to a more expressive
                # configuration format is made.
                repo_data = {
                    "collection_type": None,
                    "description": None,
                    "legal_uris": None,
                    "name": None,
                    "refresh_seconds": None,
                    "registered": None,
                    "registration_uri": None,
                    "related_uris": None,
                    "sort_policy": None,
                }

                for key in repo_data:
                        try:
                                val = cp.get(s, "repo.%s" % key)
                                if key.endswith("_uris"):
                                        val = self.read_list(val)
                                        if val == "None":
                                                val = []
                                else:
                                        if val == "None":
                                                val = None
                                repo_data[key] = val
                        except ConfigParser.NoOptionError:
                                if key.endswith("_uris"):
                                        repo_data[key] = []
                                else:
                                        repo_data[key] = None

                # Normalize/sanitize repository data.
                val = repo_data["registered"]
                if val is not None and val.lower() in ("true", "yes", "1"):
                        repo_data["registered"] = True
                else:
                        repo_data["registered"] = False

                for attr in ("collection_type", "sort_policy"):
                        if not repo_data[attr]:
                                # Assume default value for attr.
                                del repo_data[attr]

                if repo_data["refresh_seconds"] is None:
                        repo_data["refresh_seconds"] = \
                            REPO_REFRESH_SECONDS_DEFAULT

                # Guard against invalid configuration for ssl information. If
                # this isn't done, the user won't be able to load the client
                # to fix the problem.
                for origin in origins:
                        if not origin.startswith("https"):
                                ssl_key = None
                                ssl_cert = None
                                break

                #
                # For zones, where the reachability of an absolute path
                # changes depending on whether you're in the zone or not.  So
                # we have a different policy: ssl_key and ssl_cert are treated
                # as zone root relative.
                #
                ngz = self.variants.get("variant.opensolaris.zone",
                    "global") == "nonglobal"

                if ssl_key:
                        if ngz:
                                ssl_key = os.path.normpath(self.__imgroot +
                                    os.sep + ssl_key)
                        else:
                                ssl_key = os.path.abspath(ssl_key)
                        if not os.path.exists(ssl_key):
                                logger.error(api_errors.NoSuchKey(ssl_key,
                                    uri=list(origins)[0], publisher=prefix))
                                ssl_key = None

                if ssl_cert:
                        if ngz:
                                ssl_cert = os.path.normpath(self.__imgroot +
                                    os.sep + ssl_cert)
                        else:
                                ssl_cert = os.path.abspath(ssl_cert)
                        if not os.path.exists(ssl_cert):
                                logger.error(api_errors.NoSuchCertificate(
                                    ssl_cert, uri=list(origins)[0],
                                    publisher=prefix))
                                ssl_cert = None

                r = publisher.Repository(**repo_data)
                if sysrepo_uristr != "None" and sysrepo_sock_path != "None":
                        r.set_system_repo(sysrepo_uristr,
                            socket_path=sysrepo_sock_path)
                for o in origins:
                        r.add_origin(o, ssl_cert=ssl_cert, ssl_key=ssl_key)
                for m in mirrors:
                        r.add_mirror(m, ssl_cert=ssl_cert, ssl_key=ssl_key)

                # Root directory for this publisher's metadata.
                pmroot = os.path.join(meta_root, prefix)

                pub = publisher.Publisher(prefix, alias=alias,
                    client_uuid=client_uuid, disabled=disabled,
                    meta_root=pmroot, repositories=[r], sticky=sticky,
                    ca_certs=ca_certs, inter_certs=inter_certs, props=props,
                    revoked_ca_certs=revoked_ca_certs,
                    approved_ca_certs=approved_ca_certs)

                # write out the UUID if it was set
                if pub.client_uuid != client_uuid:
                        changed = True

                return prefix, pub, changed

        def __get_prop(self, name):
                """Accessor method for properties dictionary"""
                return self.__properties[name]

        def __validate_properties(self):
                """Check that properties are consistent with each other."""

                if self.__properties[SIGNATURE_POLICY] == "require-names":
                        if not self.__properties.get("signature-required-names",
                            None):
                                raise api_errors.InvalidPropertyValue(_(
                                    "At least one name must be provided for "
                                    "the signature-required-names policy."))

        def __set_prop(self, name, values):
                """Accessor method to add a property"""

                if name == SIGNATURE_POLICY:
                        if isinstance(values, basestring):
                                values = [values]
                        policy_name = values[0]
                        if policy_name not in sigpolicy.Policy.policies():
                                raise api_errors.InvalidPropertyValue(_(
                                    "%(val)s is not a valid value for this "
                                    "property:%(prop)s") % {"val": policy_name,
                                    "prop": SIGNATURE_POLICY})
                        self.__properties[SIGNATURE_POLICY] = policy_name
                        if policy_name == "require-names":
                                # If __delay_validation is set, then it's
                                # possible that signature-required-names was
                                # set by a previous line in the cfg_cache
                                # file.  If so, don't overwrite the values
                                # that have already been read.
                                if self.__delay_validation:
                                        self.__properties.setdefault(
                                            "signature-required-names", [])
                                        self.__properties[
                                            "signature-required-names"].extend(
                                            values[1:])
                                else:
                                        self.__properties[
                                            "signature-required-names"] = \
                                            values[1:]
                        else:
                                if len(values) > 1:
                                        raise api_errors.InvalidPropertyValue(
                                            _("The %s signature-policy takes "
                                            "no argument.") % policy_name)
                elif name == "signature-required-names":
                        if isinstance(values, basestring):
                                values = self.read_list(values)
                        self.__properties[name] = values
                elif name == "trust-anchor-directory":
                        if isinstance(values, list):
                                if len(values) > 1:
                                        raise api_errors.InvalidPropertyValue(
                                            _("%(name)s is not a multivalued "
                                            "property. Values are:%(value)r") %
                                            {"name":name, "value":values})
                                values = values[0]
                        self.__properties[name] = values
                else:
                        self.__properties[name] = values
                if not self.__delay_validation:
                        self.__validate_properties()

        def __del_prop(self, name):
                """Accessor method for properties"""
                del self.__properties[name]

        def __prop_iter(self):
                return self.__properties.__iter__()

        def __prop_iteritems(self):
                """Support iteritems on properties"""
                return self.__properties.iteritems()

        def __prop_keys(self):
                """Support keys() on properties"""
                return self.__properties.keys()

        def __prop_values(self):
                """Support values() on properties"""
                return self.__properties.values()

        def __prop_getdefault(self, name, value):
                return self.__properties.get(name, value)

        def __prop_setdefault(self, name, value):
                return self.__properties.setdefault(name, value)

        def __prop_update(self, d):
                return self.__properties.update(d)

        # properties so we can enforce rules

        publisher_search_order = property(lambda self: self.__publisher_search_order[:])
        preferred_publisher = property(__get_preferred_publisher, __set_preferred_publisher,
            doc="The publisher we prefer - first non-disabled publisher in search order")
        publishers = DictProperty(__get_publisher, __set_publisher, __del_publisher,
            __publisher_iteritems, __publisher_keys, __publisher_values, __publisher_iter,
            doc="A dict mapping publisher prefixes to publisher objects")

        properties = DictProperty(__get_prop, __set_prop, __del_prop,
            __prop_iteritems, __prop_keys, __prop_values, __prop_iter,
            doc="A dict holding the properties for an image.",
            fgetdefault=__prop_getdefault, fsetdefault=__prop_setdefault,
            update=__prop_update)
