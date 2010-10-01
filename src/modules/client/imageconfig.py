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

import pkg.client.api_errors as apx
import pkg.client.publisher as publisher
import pkg.config as cfg
import pkg.facet as facet
import pkg.fmri as fmri
import pkg.misc as misc
import pkg.portable as portable
import pkg.client.sigpolicy as sigpolicy
import pkg.variant as variant

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
        CA_PATH: os.path.join(os.path.sep, "etc", "openssl", "certs"),
        # Path default is intentionally relative for this case.
        "trust-anchor-directory": os.path.join("etc", "certs", "CA"),
}

# Assume the repository metadata should be checked no more than once every
# 4 hours.
REPO_REFRESH_SECONDS_DEFAULT = 4 * 60 * 60

# names of image configuration files managed by this module
CFG_FILE = "cfg_cache"
DA_FILE = "disabled_auth"

# Token used for default values.
DEF_TOKEN = "DEFAULT"
_val_map_none = { "None": None }

class ImageConfig(cfg.FileConfig):
        """An ImageConfig object is a collection of configuration information:
        URLs, publishers, properties, etc. that allow an Image to operate."""

        # This dictionary defines the set of default properties and property
        # groups for a repository configuration indexed by version.
        __defs = {
            3: [
                cfg.PropertySection("property", properties=[
                    cfg.PropPublisher("preferred-authority"),
                    cfg.PropList("publisher-search-order"),
                    cfg.PropBool(FLUSH_CONTENT_CACHE,
                        default=default_policies[FLUSH_CONTENT_CACHE]),
                    cfg.PropBool(MIRROR_DISCOVERY,
                        default=default_policies[MIRROR_DISCOVERY]),
                    cfg.PropBool(SEND_UUID,
                        default=default_policies[SEND_UUID]),
                    cfg.PropDefined(SIGNATURE_POLICY,
                        allowed=list(sigpolicy.Policy.policies()) + [DEF_TOKEN],
                        default=DEF_TOKEN),
                    cfg.Property(CA_PATH,
                        default=default_properties[CA_PATH]),
                    cfg.Property("trust-anchor-directory",
                        default=DEF_TOKEN),
                    cfg.PropList("signature-required-names"),
                ]),
                cfg.PropertySection("facet", properties=[
                    cfg.PropertyTemplate("^facet\..*", prop_type=cfg.PropBool),
                ]),
                cfg.PropertySection("variant", properties=[]),
                cfg.PropertySectionTemplate("^authority_.*", properties=[
                    # Base publisher information.
                    cfg.PropPublisher("alias", value_map=_val_map_none),
                    cfg.PropPublisher("prefix", value_map=_val_map_none),
                    cfg.PropBool("disabled"),
                    cfg.PropBool("sticky"),
                    cfg.PropUUID("uuid", value_map=_val_map_none),
                    # Publisher transport information.
                    cfg.PropPubURIList("mirrors",
                        value_map=_val_map_none),
                    cfg.PropPubURI("origin", value_map=_val_map_none),
                    cfg.PropPubURIList("origins",
                        value_map=_val_map_none),
                    cfg.Property("ssl_cert", value_map=_val_map_none),
                    cfg.Property("ssl_key", value_map=_val_map_none),
                    # Publisher signing information.
                    cfg.PropDefined("property.%s" % SIGNATURE_POLICY,
                        allowed=list(sigpolicy.Policy.policies()) + [DEF_TOKEN],
                        default=DEF_TOKEN),
                    cfg.PropList("property.signature-required-names"),
                    cfg.PropList("intermediate_certs"),
                    cfg.PropList("approved_ca_certs"),
                    cfg.PropList("revoked_ca_certs"),
                    cfg.PropList("signing_ca_certs"),
                    # Publisher repository metadata.
                    cfg.PropDefined("repo.collection_type", ["core",
                        "supplemental"], default="core",
                        value_map=_val_map_none),
                    cfg.PropDefined("repo.description",
                        value_map=_val_map_none),
                    cfg.PropList("repo.legal_uris", value_map=_val_map_none),
                    cfg.PropDefined("repo.name", default="package repository",
                        value_map=_val_map_none),
                    cfg.Property("repo.refresh_seconds",
                        default=str(REPO_REFRESH_SECONDS_DEFAULT),
                        value_map=_val_map_none),
                    cfg.PropBool("repo.registered", value_map=_val_map_none),
                    cfg.Property("repo.registration_uri",
                        value_map=_val_map_none),
                    cfg.PropList("repo.related_uris",
                        value_map=_val_map_none),
                    cfg.Property("repo.sort_policy", value_map=_val_map_none),
                ]),
            ],
        }

        def __init__(self, cfgpathname, imgroot, pubroot,
            overrides=misc.EmptyDict):
                self.__imgroot = imgroot
                self.__pubroot = pubroot
                self.__publishers = {}
                self.__validate = False
                self.facets = facet.Facets()
                self.variants = variant.Variants()
                cfg.FileConfig.__init__(self, cfgpathname,
                    definitions=self.__defs, overrides=overrides, version=3)

        def __str__(self):
                return "%s\n%s" % (self.__publishers, self)

        def remove_publisher(self, prefix):
                """External functional interface - use property interface"""
                del self.publishers[prefix]
                self.remove_section("authority_%s" % prefix)

        def change_publisher_search_order(self, new_world_order):
                """Change search order to desired value"""
                pval = self.get_property("property", "publisher-search-order")
                if sorted(new_world_order) != sorted(pval):
                        raise ValueError, "publishers added or removed"
                self.set_property("property", "publisher-search-order",
                    new_world_order)

        def __get_publisher(self, prefix):
                """Accessor method for publishers dictionary"""
                return self.__publishers[prefix]

        def __set_publisher(self, prefix, pubobj):
                """Accessor method to keep search order correct on insert"""
                pval = self.get_property("property", "publisher-search-order")
                if prefix not in pval:
                        self.add_property_value("property",
                            "publisher-search-order", prefix)
                self.__publishers[prefix] = pubobj

        def __del_publisher(self, prefix):
                """Accessor method for publishers"""
                pval = self.get_property("property", "publisher-search-order")
                if prefix in pval:
                        self.remove_property_value("property",
                            "publisher-search-order", prefix)
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
                return str(self.get_policy_str(policy)).lower() in ("true",
                    "yes")

        def get_policy_str(self, policy):
                """Return the string value for the named policy.  Returns
                the default value for the policy if the named policy is
                not defined in the image configuration.
                """
                assert policy in default_policies
                return self.get_property("property", policy)

        def get_property(self, section, name):
                """Returns the value of the property object matching the given
                section and name.  Raises UnknownPropertyError if it does not
                exist.
                """
                if name == "preferred-publisher":
                        name = "preferred-authority"
                rval = cfg.FileConfig.get_property(self, section, name)
                if name in default_policies and rval == DEF_TOKEN:
                        return default_policies[name]
                if name in default_properties and rval == DEF_TOKEN:
                        return default_properties[name]
                return rval

        def reset(self, overrides=misc.EmptyDict):
                """Discards current configuration state and returns the
                configuration object to its initial state.

                'overrides' is an optional dictionary of property values indexed
                by section name and property name.  If provided, it will be used
                to override any default values initially assigned during reset.
                """

                # Set __validate to be False so that the order the properties
                # are set here doesn't matter.
                self.__validate = False

                # Allow parent class to populate property data first.
                cfg.FileConfig.reset(self, overrides=overrides)

                #
                # Now transform property data as needed and populate image
                # configuration data structures.
                #

                # Must load variants first, since in the case of zones, the
                # variant can impact the processing of publishers.  (Notably,
                # how ssl cert and key paths are interpreted.)
                idx = self.get_index()
                self.variants.update(idx.get("variant", {}))
                self.facets.update(idx.get("facet", {}))

                # Ensure architecture and zone variants are defined.
                if "variant.arch" not in self.variants:
                        self.variants["variant.arch"] = platform.processor()
                if "variant.opensolaris.zone" not in self.variants:
                        self.variants["variant.opensolaris.zone"] = "global"

                # Merge disabled publisher file with configuration; the DA_FILE
                # is used for compatibility with older clients.
                dafile = os.path.join(os.path.dirname(self.target), DA_FILE)
                if os.path.exists(dafile):
                        # Merge disabled publisher configuration data.
                        disabled_cfg = cfg.FileConfig(dafile,
                            definitions=self.__defs, version=3)
                        for s in disabled_cfg.get_sections():
                                if s.name.startswith("authority_"):
                                        self.add_section(s)

                        # Get updated configuration index.
                        idx = self.get_index()

                preferred_publisher = None
                for s, v in idx.iteritems():
                        if re.match("authority_.*", s):
                                k, a = self.read_publisher(self.__pubroot, s, v)
                                self.publishers[k] = a
                                # just in case there's no other indication
                                if preferred_publisher is None:
                                        preferred_publisher = k

                # Move any properties found in policy section (from older
                # images) to the property section.
                for k, v in idx.get("policy", {}).iteritems():
                        self.set_property("property", k, v)
                        self.remove_property("policy", k)

                # Setup defaults for properties that have no value.
                if not self.get_property("property", CA_PATH):
                        self.set_property("property", CA_PATH,
                            default_properties[CA_PATH])

                pso = self.get_property("property", "publisher-search-order")
                if not pso and preferred_publisher:
                        # make up the default - preferred, then the rest in
                        # alpha order
                        pso = [preferred_publisher]

                # Ensure that all configured publishers are present in
                # search order (add them in alpha order to the end).
                # Also ensure that all publishers in search order that
                # are not known are removed.
                known_pubs = set(self.__publishers.keys())
                sorted_pubs = set(pso)
                new_pubs = known_pubs - sorted_pubs
                old_pubs = sorted_pubs - known_pubs
                for pub in old_pubs:
                        pso.remove(pub)
                pso.extend(sorted(new_pubs))
                self.set_property("property", "publisher-search-order", pso)

                # Now re-enable validation and validate the properties.
                self.__validate = True
                self.__validate_properties()

                # Finally, attempt to write configuration again to ensure
                # changes are reflected on-disk.
                self.write(ignore_unprivileged=True)

        def set_property(self, section, name, value):
                """Sets the value of the property object matching the given
                section and name.  If the section or property does not already
                exist, it will be added.  Raises InvalidPropertyValueError if
                the value is not valid for the given property."""

                if name == "preferred-publisher":
                        # Ensure that whenever preferred-publisher is changed,
                        # search order is updated as well.  In addition, ensure
                        # that 'preferred-publisher' is always stored as
                        # 'preferred-authority' internally for compatibility
                        # with older clients.
                        name = "preferred-authority"
                        pso = self.get_property("property",
                            "publisher-search-order")
                        if value in pso:
                                pso.remove(value)
                        pso.insert(0, value)
                cfg.FileConfig.set_property(self, section, name, value)

                if self.__validate:
                        self.__validate_properties()

        def set_properties(self, properties):
                """Sets the values of the property objects matching those found
                in the provided dictionary.  If any section or property does not
                already exist, it will be added.  An InvalidPropertyValueError
                will be raised if the value is not valid for the given
                properties.

                'properties' should be a dictionary of dictionaries indexed by
                section and then by property name.  As an example:

                    {
                        'section': {
                            'property': value
                        }
                    }
                """

                # Validation must be delayed until after all properties are set,
                # in case some properties are interdependent for validation.
                self.__validate = False
                try:
                        cfg.FileConfig.set_properties(self, properties)
                finally:
                        # Ensure validation is re-enabled even if an exception
                        # is raised.
                        self.__validate = True

                self.__validate_properties()

        def write(self, ignore_unprivileged=False):
                """Write the image configuration."""

                # Force preferred-authority to match publisher-search-order.
                pso = self.get_property("property", "publisher-search-order")
                ppub = None
                for p in pso:
                        if not self.__publishers[p].disabled:
                                ppub = p
                                break
                else:
                        if pso:
                                # Fallback to first publisher in the unlikley
                                # case that all publishers in search order are
                                # disabled.
                                ppub = pso[0]
                self.set_property("property", "preferred-authority", ppub)

                # The variant and facet sections must be removed so that the
                # private variant and facet objects can have their information
                # transferred to the configuration object verbatim.
                try:
                        self.remove_section("variant")
                except cfg.UnknownSectionError:
                        pass
                for f in self.variants:
                        self.set_property("variant", f, self.variants[f])

                try:
                        self.remove_section("facet")
                except cfg.UnknownSectionError:
                        pass
                for f in self.facets:
                        self.set_property("facet", f, self.facets[f])

                # Transfer current publisher information to configuration.
                da_path = os.path.join(os.path.dirname(self.target), DA_FILE)
                if os.path.exists(da_path):
                        # Ensure existing information is ignored during write.
                        try:
                                portable.remove(da_path)
                        except EnvironmentError, e:
                                exc = apx._convert_error(e)
                                if not isinstance(exc, apx.PermissionsException) or \
                                    not ignore_unprivileged:
                                        raise exc

                # For compatibility with older clients, enabled and disabled
                # publishers are written to separate configuration files.
                disabled_cfg = cfg.FileConfig(da_path, definitions=self.__defs,
                    version=3)
                disabled_cfg.remove_section("property")
                disabled = []
                for prefix in self.__publishers:
                        pub = self.__publishers[prefix]
                        section = "authority_%s" % pub.prefix

                        c = self
                        if pub.disabled:
                                # Ensure disabled publishers are removed from
                                # base configuration.
                                try:
                                        self.remove_section(section)
                                except cfg.UnknownSectionErro:
                                        pass
                                c = disabled_cfg

                        for prop in ("alias", "prefix", "signing_ca_certs",
                            "approved_ca_certs", "revoked_ca_certs",
                            "intermediate_certs", "disabled", "sticky"):
                                c.set_property(section, prop,
                                    getattr(pub, prop))

                        # For now, write out "origin" for compatibility with
                        # older clients in addition to "origins".  Older
                        # clients may drop the "origins" when rewriting the
                        # configuration, but that doesn't really break
                        # anything.
                        repo = pub.selected_repository
                        c.set_property(section, "origin", repo.origins[0].uri)

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
                        c.set_property(section, "ssl_key", p)

                        p = str(pub["ssl_cert"])
                        if ngz and self.__imgroot != os.sep and p != "None":
                                if p.startswith(self.__imgroot):
                                        p = p[len(self.__imgroot):]
                        c.set_property(section, "ssl_cert", p)

                        # XXX this should really be client_uuid, but is being
                        # left with this name for compatibility with older
                        # clients.
                        c.set_property(section, "uuid", pub.client_uuid)

                        # Write selected repository data.
                        for prop in ("origins", "mirrors", "collection_type",
                            "description", "legal_uris", "name",
                            "refresh_seconds", "registered", "registration_uri",
                            "related_uris", "sort_policy"):
                                pval = getattr(repo, prop)
                                if isinstance(pval, list):
                                        # Stringify lists of objects; this
                                        # assumes the underlying objects
                                        # can be stringified properly.
                                        pval = [str(v) for v in pval]

                                cfg_key = prop
                                if prop not in ("origins", "mirrors"):
                                        # All other properties need to be
                                        # prefixed.
                                        cfg_key = "repo.%s" % cfg_key
                                if prop == "registration_uri":
                                        # Must be stringified.
                                        pval = str(pval)
                                c.set_property(section, cfg_key, pval)

                        secobj = c.get_section(section)
                        for pname in secobj.get_index():
                                if pname.startswith("property.") and \
                                    pname[len("property."):] not in pub.properties:
                                        # Ensure properties not currently set
                                        # for the publisher are removed from
                                        # the existing configuration.
                                        secobj.remove_property(pname)

                        for key, val in pub.properties.iteritems():
                                if val == DEF_TOKEN:
                                        continue
                                c.set_property(section, "property.%s" % key,
                                    val)

                        if pub.disabled:
                                # Track any sections for disabled publishers
                                # so they can be merged with the base config
                                # later.
                                disabled.append(c.get_section(section))

                # Write configuration only if configuration directory exists;
                # this is to prevent failure during the early stages of image
                # creation.
                if os.path.exists(os.path.dirname(self.target)):
                        # Ensure properties with the special value of DEF_TOKEN
                        # are never written so that if the default value is
                        # changed later, clients will automatically get that
                        # value instead of the previous one.
                        default = []
                        for name in (default_properties.keys() +
                            default_policies.keys()):
                                # The actual class method must be called here as
                                # ImageConfig's set_property can return the
                                # value that maps to 'DEFAULT' instead.
                                secobj = self.get_section("property")
                                try:
                                        propobj = secobj.get_property(name)
                                except cfg.UnknownPropertyError:
                                        # Property was removed, so skip it.
                                        continue

                                if propobj.value == DEF_TOKEN:
                                        default.append(name)
                                        secobj.remove_property(name)

                        try:
                                cfg.FileConfig.write(self)
                                if not [s for s in disabled_cfg.get_sections()]:
                                        # If there are no disabled publishers,
                                        # ensure that DA_FILE is removed if it
                                        # exists.
                                        try:
                                                portable.remove(
                                                    disabled_cfg.target)
                                        except OSError, e:
                                                if e.errno != errno.ENOENT:
                                                        raise apx._convert_error(e)
                                else:
                                        # Disabled publishers to write out;
                                        # these are written to a separate file
                                        # for compatibility with older clients.
                                        disabled_cfg.write()
                        except apx.PermissionsException:
                                if not ignore_unprivileged:
                                        raise
                        finally:
                                # Merge default props back into configuration.
                                for name in default:
                                        self.set_property("property", name,
                                            DEF_TOKEN)

                # Merge disabled publishers back into base configuration.
                map(self.add_section, disabled)

        def read_publisher(self, meta_root, sname, sec_idx):
                # s is the section of the config file.
                # publisher block has alias, prefix, origin, and mirrors
                changed = False

                # Ensure that the list of origins is unique and complete;
                # add 'origin' to list of origins if it doesn't exist already.
                origins = set(sec_idx["origins"])
                origin = sec_idx["origin"]
                if origin:
                        origins.add(origin)

                props = {}
                for k, v in sec_idx.iteritems():
                        if not k.startswith("property."):
                                continue
                        prop_name = k[len("property."):]
                        if v == DEF_TOKEN:
                                # Discard publisher properties with the
                                # DEF_TOKEN value; allow the publisher class to
                                # handle these.
                                self.remove_property(sname, k)
                                continue
                        props[prop_name] = v

                # Load repository data.
                repo_data = {}
                for key, val in sec_idx.iteritems():
                        if key.startswith("repo."):
                                pname = key[len("repo."):]
                                repo_data[pname] = val

                # Normalize/sanitize repository data.
                for attr in ("collection_type", "sort_policy"):
                        if not repo_data[attr]:
                                # Assume default value for attr.
                                del repo_data[attr]

                if repo_data["refresh_seconds"] == "":
                        repo_data["refresh_seconds"] = \
                            str(REPO_REFRESH_SECONDS_DEFAULT)

                # Guard against invalid configuration for ssl information. If
                # this isn't done, the user won't be able to load the client
                # to fix the problem.
                ssl_key = sec_idx["ssl_key"]
                ssl_cert = sec_idx["ssl_cert"]
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
                prefix = sec_idx["prefix"]
                ngz = self.variants["variant.opensolaris.zone"] == "nonglobal"
                if ssl_key:
                        if ngz:
                                ssl_key = os.path.normpath(self.__imgroot +
                                    os.sep + ssl_key)
                        else:
                                ssl_key = os.path.abspath(ssl_key)
                        if not os.path.exists(ssl_key):
                                logger.error(apx.NoSuchKey(ssl_key,
                                    uri=list(origins)[0], publisher=prefix))
                                ssl_key = None

                if ssl_cert:
                        if ngz:
                                ssl_cert = os.path.normpath(self.__imgroot +
                                    os.sep + ssl_cert)
                        else:
                                ssl_cert = os.path.abspath(ssl_cert)
                        if not os.path.exists(ssl_cert):
                                logger.error(apx.NoSuchCertificate(
                                    ssl_cert, uri=list(origins)[0],
                                    publisher=prefix))
                                ssl_cert = None

                r = publisher.Repository(**repo_data)
                for o in origins:
                        r.add_origin(o, ssl_cert=ssl_cert, ssl_key=ssl_key)
                for m in sec_idx["mirrors"]:
                        r.add_mirror(m, ssl_cert=ssl_cert, ssl_key=ssl_key)

                # Root directory for this publisher's metadata.
                pmroot = os.path.join(meta_root, prefix)

                pub = publisher.Publisher(prefix, alias=sec_idx["alias"],
                    client_uuid=sec_idx["uuid"], disabled=sec_idx["disabled"],
                    meta_root=pmroot, repositories=[r],
                    sticky=sec_idx["sticky"],
                    ca_certs=sec_idx["signing_ca_certs"],
                    intermediate_certs=sec_idx["intermediate_certs"],
                    props=props, revoked_ca_certs=sec_idx["revoked_ca_certs"],
                    approved_ca_certs=sec_idx["approved_ca_certs"])

                if pub.client_uuid != sec_idx["uuid"]:
                        # Publisher has generated new uuid; ensure configuration
                        # matches.
                        self.set_property(sname, "uuid", pub.client_uuid)

                return prefix, pub

        def __validate_properties(self):
                """Check that properties are consistent with each other."""

                try:
                        polval = self.get_property("property", SIGNATURE_POLICY)
                except cfg.PropertyConfigError:
                        # If it hasn't been set yet, there's nothing to 
                        # validate.
                        return

                if polval == "require-names":
                        signames = self.get_property("property",
                            "signature-required-names")
                        if not signames: 
                                raise apx.InvalidPropertyValue(_(
                                    "At least one name must be provided for "
                                    "the signature-required-names policy."))

        # properties so we can enforce rules
        publishers = DictProperty(__get_publisher, __set_publisher,
            __del_publisher, __publisher_iteritems, __publisher_keys,
            __publisher_values, __publisher_iter,
            doc="A dict mapping publisher prefixes to publisher objects")
