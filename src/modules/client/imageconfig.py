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

import errno
import os.path
import platform
import re
import urllib

from pkg.client import global_settings
logger = global_settings.logger

import pkg.client.api_errors as apx
import pkg.client.publisher as publisher
import pkg.client.sigpolicy as sigpolicy
import pkg.client.linkedimage as li
import pkg.config as cfg
import pkg.facet as facet
import pkg.misc as misc
import pkg.pkgsubprocess as subprocess
import pkg.portable as portable
import pkg.smf as smf
import pkg.variant as variant

from pkg.misc import DictProperty, SIGNATURE_POLICY
from pkg.client.debugvalues import DebugValues
from pkg.client.transport.exception import TransportFailures
# The default_policies dictionary defines the policies that are supported by
# pkg(5) and their default values. Calls to the ImageConfig.get_policy method
# should use the constants defined here.

BE_POLICY = "be-policy"
FLUSH_CONTENT_CACHE = "flush-content-cache-on-success"
MIRROR_DISCOVERY = "mirror-discovery"
SEND_UUID = "send-uuid"
USE_SYSTEM_REPO = "use-system-repo"
CHECK_CERTIFICATE_REVOCATION = "check-certificate-revocation"

default_policies = {
    BE_POLICY: "default",
    CHECK_CERTIFICATE_REVOCATION: False,
    FLUSH_CONTENT_CACHE: True,
    MIRROR_DISCOVERY: False,
    SEND_UUID: True,
    SIGNATURE_POLICY: sigpolicy.DEFAULT_POLICY,
    USE_SYSTEM_REPO: False
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

CURRENT_VERSION = 3

class ImageConfig(cfg.FileConfig):
        """An ImageConfig object is a collection of configuration information:
        URLs, publishers, properties, etc. that allow an Image to operate."""

        # This dictionary defines the set of default properties and property
        # groups for an image configuration indexed by version.
        __defs = {
            2: [
                cfg.PropertySection("filter", properties=[]),
                cfg.PropertySection("image", properties=[
                    cfg.PropInt("version"),
                ]),
                cfg.PropertySection("property", properties=[
                    cfg.PropList("publisher-search-order"),
                    cfg.PropPublisher("preferred-authority"),
                    cfg.PropBool("display-coprights", default=True),
                    cfg.PropBool("require-optional", default=False),
                    cfg.PropBool("pursue-latest", default=True),
                    cfg.PropBool(FLUSH_CONTENT_CACHE,
                        default=default_policies[FLUSH_CONTENT_CACHE]),
                    cfg.PropBool(SEND_UUID,
                        default=default_policies[SEND_UUID]),
                ]),
                cfg.PropertySection("variant", properties=[]),
                cfg.PropertySectionTemplate("^authority_.*", properties=[
                    # Base publisher information.
                    cfg.PropPublisher("alias", value_map=_val_map_none),
                    cfg.PropPublisher("prefix", value_map=_val_map_none),
                    cfg.PropBool("disabled"),
                    cfg.PropUUID("uuid", value_map=_val_map_none),
                    # Publisher transport information.
                    cfg.PropPubURIList("mirrors",
                        value_map=_val_map_none),
                    cfg.PropPubURI("origin", value_map=_val_map_none),
                    cfg.Property("ssl_cert", value_map=_val_map_none),
                    cfg.Property("ssl_key", value_map=_val_map_none),
                    # Publisher repository metadata.
                    cfg.PropDefined("repo.collection_type", ["core",
                        "supplemental"], default="core",
                        value_map=_val_map_none),
                    cfg.PropDefined("repo.description",
                        value_map=_val_map_none),
                    cfg.PropList("repo.legal_uris", value_map=_val_map_none),
                    cfg.PropDefined("repo.name", default="package repository",
                        value_map=_val_map_none),
                    # Must be a string so "" can be stored.
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
            3: [
                cfg.PropertySection("image", properties=[
                    cfg.PropInt("version"),
                ]),
                # The preferred-authority property should be removed from
                # version 4 of image config.
                cfg.PropertySection("property", properties=[
                    cfg.PropPublisher("preferred-authority"),
                    cfg.PropList("publisher-search-order"),
                    cfg.PropDefined(BE_POLICY, allowed=["default",
                        "always-new", "create-backup", "when-required"],
                        default=default_policies[BE_POLICY]),
                    cfg.PropBool(FLUSH_CONTENT_CACHE,
                        default=default_policies[FLUSH_CONTENT_CACHE]),
                    cfg.PropBool(MIRROR_DISCOVERY,
                        default=default_policies[MIRROR_DISCOVERY]),
                    cfg.PropBool(SEND_UUID,
                        default=default_policies[SEND_UUID]),
                    cfg.PropDefined(SIGNATURE_POLICY,
                        allowed=list(sigpolicy.Policy.policies()) + [DEF_TOKEN],
                        default=DEF_TOKEN),
                    cfg.PropBool(USE_SYSTEM_REPO,
                        default=default_policies[USE_SYSTEM_REPO]),
                    cfg.Property(CA_PATH,
                        default=default_properties[CA_PATH]),
                    cfg.Property("trust-anchor-directory",
                        default=DEF_TOKEN),
                    cfg.PropList("signature-required-names"),
                    cfg.Property(CHECK_CERTIFICATE_REVOCATION,
                        default=default_policies[
                            CHECK_CERTIFICATE_REVOCATION])
                ]),
                cfg.PropertySection("facet", properties=[
                    cfg.PropertyTemplate("^facet\..*", prop_type=cfg.PropBool),
                ]),
                cfg.PropertySection("mediators", properties=[
                    cfg.PropertyTemplate("^[A-Za-z0-9\-]+\.implementation$"),
                    cfg.PropertyTemplate("^[A-Za-z0-9\-]+\.implementation-version$",
                        prop_type=cfg.PropVersion),
                    cfg.PropertyTemplate("^[A-Za-z0-9\-]+\.implementation-source$",
                        prop_type=cfg.PropDefined, allowed=["site", "vendor",
                        "local", "system"], default="local"),
                    cfg.PropertyTemplate("^[A-Za-z0-9\-]+\.version$",
                        prop_type=cfg.PropVersion),
                    cfg.PropertyTemplate("^[A-Za-z0-9\-]+\.version-source$",
                        prop_type=cfg.PropDefined, allowed=["site", "vendor",
                        "local", "system"], default="local"),
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
                    cfg.PropList("property.proxied-urls"),
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
                    # Must be a string so "" can be stored.
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
                cfg.PropertySectionTemplate("^linked_.*", properties=[
                    cfg.Property(li.PROP_NAME, value_map=_val_map_none),
                    cfg.Property(li.PROP_PATH, value_map=_val_map_none),
                    cfg.PropBool(li.PROP_RECURSE, default=True),
                ]),
            ],
        }

        def __init__(self, cfgpathname, imgroot, overrides=misc.EmptyDict,
            version=None):
                self.__imgroot = imgroot
                self.__publishers = {}
                self.__validate = False
                self.facets = facet.Facets()
                self.mediators = {}
                self.variants = variant.Variants()
                self.linked_children = {}
                cfg.FileConfig.__init__(self, cfgpathname,
                    definitions=self.__defs, overrides=overrides,
                    version=version)

        def __str__(self):
                return "%s\n%s" % (self.__publishers, self.__defs)

        def remove_publisher(self, prefix):
                """External functional interface - use property interface"""
                del self.publishers[prefix]

        def change_publisher_search_order(self, being_moved, staying_put,
            after):
                """Change the publisher search order by moving the publisher
                'being_moved' relative to the publisher 'staying put.'  The
                boolean 'after' determins whether 'being_moved' is placed before
                or after 'staying_put'."""

                so = self.get_property("property", "publisher-search-order")
                so.remove(being_moved)
                try:
                        ind = so.index(staying_put)
                except ValueError:
                        raise apx.MoveRelativeToUnknown(staying_put)
                if after:
                        so.insert(ind + 1, being_moved)
                else:
                        so.insert(ind, being_moved)
                self.set_property("property", "publisher-search-order", so)

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
                try:
                        self.remove_section("authority_%s" % prefix)
                except cfg.UnknownSectionError:
                        pass
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
                # facets are encoded so they can contain '/' characters.
                for k, v in idx.get("facet", {}).iteritems():
                        self.facets[urllib.unquote(k)] = v


                # Ensure architecture and zone variants are defined.
                if "variant.arch" not in self.variants:
                        self.variants["variant.arch"] = platform.processor()
                if "variant.opensolaris.zone" not in self.variants:
                        self.variants["variant.opensolaris.zone"] = "global"

                # load linked image child properties
                for s, v in idx.iteritems():
                        if not re.match("linked_.*", s):
                                continue
                        linked_props = self.read_linked(s, v)
                        if linked_props:
                                lin = linked_props[li.PROP_NAME]
                                assert lin not in self.linked_children
                                self.linked_children[lin] = linked_props

                # Merge disabled publisher file with configuration; the DA_FILE
                # is used for compatibility with older clients.
                dafile = os.path.join(os.path.dirname(self.target), DA_FILE)
                if os.path.exists(dafile):
                        # Merge disabled publisher configuration data.
                        disabled_cfg = cfg.FileConfig(dafile,
                            definitions=self.__defs, version=self.version)
                        for s in disabled_cfg.get_sections():
                                if s.name.startswith("authority_"):
                                        self.add_section(s)

                        # Get updated configuration index.
                        idx = self.get_index()

                for s, v in idx.iteritems():
                        if re.match("authority_.*", s):
                                k, a = self.read_publisher(s, v)
                                self.publishers[k] = a

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

                # Load mediator data.
                for entry, value in idx.get("mediators", {}).iteritems():
                        mname, mtype = entry.rsplit(".", 1)
                        self.mediators.setdefault(mname, {})[mtype] = value

                # Now re-enable validation and validate the properties.
                self.__validate = True
                self.__validate_properties()

                # Finally, attempt to write configuration again to ensure
                # changes are reflected on-disk -- but only if the version
                # matches most current.
                if self.version == CURRENT_VERSION:
                        self.write(ignore_unprivileged=True)

        def set_property(self, section, name, value):
                """Sets the value of the property object matching the given
                section and name.  If the section or property does not already
                exist, it will be added.  Raises InvalidPropertyValueError if
                the value is not valid for the given property."""

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

                # The variant, facet, and mediator sections must be removed so
                # the private copies can be transferred to the configuration
                # object.
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
                        self.set_property("facet", urllib.quote(f, ""), 
                            self.facets[f])

                try:
                        self.remove_section("mediators")
                except cfg.UnknownSectionError:
                        pass
                for mname, mvalues in self.mediators.iteritems():
                        for mtype, mvalue in mvalues.iteritems():
                                # name.implementation[-(source|version)]
                                # name.version[-source]
                                pname = mname + "." + mtype
                                self.set_property("mediators", pname, mvalue)

                # remove all linked image child configuration
                idx = self.get_index()
                for s, v in idx.iteritems():
                        if not re.match("linked_.*", s):
                                continue
                        self.remove_section(s)

                # add sections for any known linked children
                for lin in sorted(self.linked_children):
                        linked_props = self.linked_children[lin]
                        s = "linked_%s" % str(lin)
                        for k in [li.PROP_NAME, li.PROP_PATH, li.PROP_RECURSE]:
                                self.set_property(s, k, str(linked_props[k]))


                # Transfer current publisher information to configuration.
                for prefix in self.__publishers:
                        pub = self.__publishers[prefix]
                        section = "authority_%s" % pub.prefix

                        for prop in ("alias", "prefix", "approved_ca_certs",
                            "revoked_ca_certs", "disabled", "sticky"):
                                self.set_property(section, prop,
                                    getattr(pub, prop))

                        # Force removal of origin property when writing.  It
                        # should only exist when configuration is loaded if
                        # the client is using an older image.
                        try:
                                self.remove_property(section, "origin")
                        except cfg.UnknownPropertyError:
                                # Already gone.
                                pass

                        # Store SSL Cert and Key data.
                        repo = pub.repository
                        p = ""
                        for o in repo.origins:
                                if o.ssl_key:
                                        p = str(o.ssl_key)
                                        break
                        self.set_property(section, "ssl_key", p)

                        p = ""
                        for o in repo.origins:
                                if o.ssl_cert:
                                        p = str(o.ssl_cert)
                                        break
                        self.set_property(section, "ssl_cert", p)

                        # Store publisher UUID.
                        self.set_property(section, "uuid", pub.client_uuid)

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
                                self.set_property(section, cfg_key, pval)

                        secobj = self.get_section(section)
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
                                self.set_property(section, "property.%s" % key,
                                    val)

                # Write configuration only if configuration directory exists;
                # this is to prevent failure during the early stages of image
                # creation.
                if os.path.exists(os.path.dirname(self.target)):
                        # Discard old disabled publisher configuration if it
                        # exists.
                        da_path = os.path.join(os.path.dirname(self.target),
                            DA_FILE)
                        try:
                                portable.remove(da_path)
                        except EnvironmentError, e:
                                # Don't care if the file is already gone.
                                if e.errno != errno.ENOENT:
                                        exc = apx._convert_error(e)
                                        if not isinstance(exc, apx.PermissionsException) or \
                                            not ignore_unprivileged:
                                                raise exc

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
                        except apx.PermissionsException:
                                if not ignore_unprivileged:
                                        raise
                        finally:
                                # Merge default props back into configuration.
                                for name in default:
                                        self.set_property("property", name,
                                            DEF_TOKEN)

        def read_linked(self, s, sidx):
                """Read linked image properties associated with a child image.
                Zone linked images do not store their properties here in the
                image config.

                If we encounter an error while parsing property data, then
                instead of throwing an error/exception which the user would
                have no way of fixing, we simply return and ignore the child.
                The child data will be removed from the config file the next
                time it gets re-written, and if the user want the child back
                they'll have to re-attach it."""

                linked_props = dict()

                # Check for known properties
                for k in [li.PROP_NAME, li.PROP_PATH, li.PROP_RECURSE]:
                        if k not in sidx:
                                # we're missing a property
                                return None
                        linked_props[k] = sidx[k]

                # all children saved in the config file are pushed based
                linked_props[li.PROP_MODEL] = li.PV_MODEL_PUSH

                # make sure the name is valid
                try:
                        lin = li.LinkedImageName(linked_props[li.PROP_NAME])
                except apx.MalformedLinkedImageName:
                        # invalid child image name
                        return None
                linked_props[li.PROP_NAME] = lin

                # check if this image is already defined
                if lin in self.linked_children:
                        # duplicate child linked image data, first copy wins
                        return None

                return linked_props

        def read_publisher(self, sname, sec_idx):
                # s is the section of the config file.
                # publisher block has alias, prefix, origin, and mirrors

                # Ensure that the list of origins is unique and complete;
                # add 'origin' to list of origins if it doesn't exist already.
                origins = set(sec_idx.get("origins", []))
                origin = sec_idx.get("origin", None)
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

                prefix = sec_idx["prefix"]
                ssl_key = sec_idx["ssl_key"]
                ssl_cert = sec_idx["ssl_cert"]

                r = publisher.Repository(**repo_data)
                for o in origins:
                        if not any(o.startswith(scheme + ":")
                            for scheme in publisher.SSL_SCHEMES):
                                r.add_origin(o)
                                continue
                        r.add_origin(o, ssl_cert=ssl_cert, ssl_key=ssl_key)
                for m in sec_idx["mirrors"]:
                        if not any(m.startswith(scheme + ":")
                            for scheme in publisher.SSL_SCHEMES):
                                r.add_mirror(m)
                                continue
                        r.add_mirror(m, ssl_cert=ssl_cert, ssl_key=ssl_key)

                pub = publisher.Publisher(prefix, alias=sec_idx["alias"],
                    client_uuid=sec_idx["uuid"], disabled=sec_idx["disabled"],
                    repository=r, sticky=sec_idx.get("sticky", True),
                    props=props,
                    revoked_ca_certs=sec_idx.get("revoked_ca_certs", []),
                    approved_ca_certs=sec_idx.get("approved_ca_certs", []))

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

        def __publisher_getdefault(self, name, value):
                """Support getdefault() on properties"""
                return self.__publishers.get(name, value)

        # properties so we can enforce rules
        publishers = DictProperty(__get_publisher, __set_publisher,
            __del_publisher, __publisher_iteritems, __publisher_keys,
            __publisher_values, __publisher_iter,
            doc="A dict mapping publisher prefixes to publisher objects",
            fgetdefault=__publisher_getdefault, )


class NullSystemPublisher(object):
        """Dummy system publisher object for use when an image doesn't use a
        system publisher."""

        __supported_props = ("publisher-search-order", "property.proxied-urls")

        def __init__(self):
                self.publishers = {}
                self.__props = dict([(p, []) for p in self.__supported_props])

        def write(self):
                return

        def get_property(self, section, name):
                """Return the value of the property if the NullSystemPublisher
                has any knowledge of it."""

                if section == "property" and \
                    name in self.__supported_props:
                        return self.__props[name]
                raise NotImplementedError()

        def set_property(self, section, name, value):
                if section == "property" and name in self.__supported_props:
                        self.__props[name] = value
                        return
                raise NotImplementedError()


class BlendedConfig(object):
        """Class which handles combining the system repository configuration
        with the image configuration."""

        def __init__(self, img_cfg, pkg_counts, imgdir, transport,
            use_system_pub):
                """The 'img_cfg' parameter is the ImageConfig object for the
                image.

                The 'pkg_counts' parameter is a list of tuples which contains
                the number of packages each publisher has installed.

                The 'imgdir' parameter is the directory the current image
                resides in.

                The 'transport' object is the image's transport.

                The 'use_system_pub' parameter is a boolean which indicates
                whether the system publisher should be used."""

                self.img_cfg = img_cfg
                self.__pkg_counts = pkg_counts

                self.__proxy_url = None

                syscfg_path = os.path.join(imgdir, "pkg5.syspub")
                # load the existing system repo config
                if os.path.exists(syscfg_path):
                        old_sysconfig = ImageConfig(syscfg_path, None)
                else:
                        old_sysconfig = NullSystemPublisher()

                write_sys_cfg = True
                if use_system_pub:
                        # get new syspub data from sysdepot
                        try:
                                self.__proxy_url = os.environ["PKG_SYSREPO_URL"]
                                if not self.__proxy_url.startswith("http://"):
                                        self.__proxy_url = "http://" + \
                                            self.__proxy_url
                        except KeyError:
                                try:
                                        host = smf.get_prop(
                                            "application/pkg/zones-proxy-client",
                                            "config/listen_host")
                                        port = smf.get_prop(
                                            "application/pkg/zones-proxy-client",
                                            "config/listen_port")
                                except smf.NonzeroExitException, e:
                                        # If we can't get information out of
                                        # smf, try using pkg/sysrepo.
                                        try:
                                                host = smf.get_prop(
                                                    "application/pkg/system-repository:default",
                                                    "config/host")
                                                host = "localhost"
                                                port = smf.get_prop(
                                                    "application/pkg/system-repository:default",
                                                    "config/port")
                                        except smf.NonzeroExitException, e:
                                                raise apx.UnknownSysrepoConfiguration()
                                self.__proxy_url = "http://%s:%s" % (host, port)
                        sysdepot_uri = publisher.RepositoryURI(self.__proxy_url)
                        assert sysdepot_uri.get_host()
                        try:
                                pubs, props = transport.get_syspub_data(
                                    sysdepot_uri)
                        except TransportFailures:
                                self.sys_cfg = old_sysconfig
                                write_sys_cfg = False
                        else:
                                try:
                                        try:
                                                # Try to remove any previous
                                                # system repository
                                                # configuration.
                                                portable.remove(syscfg_path)
                                        except OSError, e:
                                                if e.errno == errno.ENOENT:
                                                        # Check to see whether
                                                        # we'll be able to write
                                                        # the configuration
                                                        # later.
                                                        with open(syscfg_path,
                                                            "wb") as fh:
                                                                fh.close()
                                                        self.sys_cfg = \
                                                            ImageConfig(
                                                            syscfg_path, None)
                                                else:
                                                        raise
                                except OSError, e:
                                        if e.errno in \
                                            (errno.EACCES, errno.EROFS):
                                                # A permissions error means that
                                                # either we couldn't remove the
                                                # existing configuration or
                                                # create a new configuration in
                                                # that place.  In that case, use
                                                # an in-memory only version of
                                                # the ImageConfig.
                                                self.sys_cfg = \
                                                    NullSystemPublisher()
                                                write_sys_cfg = False
                                        else:
                                                raise
                                else:
                                        # The previous configuration was
                                        # successfully removed, so use that
                                        # location for the new ImageConfig.
                                        self.sys_cfg = \
                                            ImageConfig(syscfg_path, None)
                                for p in pubs:
                                        assert not p.disabled, "System " \
                                            "publisher %s was unexpectedly " \
                                            "marked disabled in system " \
                                            "configuration." % p.prefix
                                        self.sys_cfg.publishers[p.prefix] = p

                                self.sys_cfg.set_property("property",
                                    "publisher-search-order",
                                    props["publisher-search-order"])
                else:
                        self.sys_cfg = NullSystemPublisher()

                self.__publishers, self.added_pubs, self.removed_pubs = \
                    self.__merge_publishers(self.img_cfg, self.sys_cfg,
                        pkg_counts, old_sysconfig, self.__proxy_url,
                        write_sys_cfg)

        @staticmethod
        def __merge_publishers(img_cfg, sys_cfg, pkg_counts, old_sysconfig,
            proxy_url, write_sys_cfg):
                """This funcion merges an old publisher configuration from the
                system repository with the new publisher configuration from the
                system repository.  It retuns a tuple containing a dictionary
                mapping prefix to publisher, the publisher objects for the newly
                added system publishers, and the publisher objects for the
                system publishers which were removed.

                The 'img_cfg' parameter is the ImageConfig object for the
                image.

                The 'sys_cfg' parameter is the ImageConfig object containing the
                publisher configuration from the system repository.

                The 'pkg_counts' parameter is a list of tuples which contains
                the number of packages each publisher has installed.

                The 'old_sysconfig' parameter is ImageConfig object containing
                the previous publisher configuration from the system repository.

                The 'use_system_pub' parameter is a boolean which indicates
                whether the system publisher should be used.

                The 'proxy_url' parameter is the url for the system repository.

                The 'write_sys_cfg' parameter indicates whether the new sys_cfg
                object should attempt to save its configuration to disk.
                """

                pubs_with_installed_pkgs = set()

                added_pubs = set()
                removed_pubs = set()

                for prefix, cnt, ver_cnt in pkg_counts:
                        if cnt > 0:
                                pubs_with_installed_pkgs.add(prefix)

                # Merge in previously existing system publishers which have
                # installed packages.
                for prefix in old_sysconfig.get_property("property",
                    "publisher-search-order"):
                        if prefix in sys_cfg.publishers or \
                            prefix in img_cfg.publishers or \
                            prefix not in pubs_with_installed_pkgs:
                                continue
                        sys_cfg.publishers[prefix] = \
                            old_sysconfig.publishers[prefix]
                        sys_cfg.publishers[prefix].disabled = True

                # Write out the new system publisher configuration.
                if write_sys_cfg:
                        sys_cfg.write()
                for p in sys_cfg.publishers.values():
                        for o in p.repository.origins:
                                o.system = True
                                if o.uri in p.properties["proxied-urls"]:
                                        o.proxy = proxy_url
                        for o in p.repository.mirrors:
                                o.system = True
                                if o.uri in p.properties["proxied-urls"]:
                                        o.proxy = proxy_url
                        p.sys_pub = True

                # Create a dictionary mapping publisher prefix to publisher
                # object while merging user configured origins into system
                # publishers.
                res = {}
                for p in sys_cfg.publishers:
                        res[p] = sys_cfg.publishers[p]
                for p in img_cfg.publishers.values():
                        assert isinstance(p, publisher.Publisher)
                        if p.prefix in res:
                                repo = p.repository
                                for o in repo.origins:
                                        res[p.prefix].repository.add_origin(o)
                                for m in repo.mirrors:
                                        res[p.prefix].repository.add_mirror(m)
                        else:
                                res[p.prefix] = p

                new_pubs = set(sys_cfg.publishers.keys())
                old_pubs = set(old_sysconfig.publishers.keys())

                # Find the system publishers which appeared or vanished.  This
                # is needed so that the catalog information can be rebuilt.
                added_pubs = new_pubs - old_pubs
                removed_pubs = old_pubs - new_pubs

                return res, [res[p] for p in added_pubs], \
                    [old_sysconfig.publishers[p] for p in removed_pubs]

        def write(self):
                """Update the image configuration to reflect any changes made,
                then write it."""

                for p in self.__publishers.values():

                        if not p.sys_pub:
                                self.img_cfg.publishers[p.prefix] = p
                                continue

                        # If we had previous user-configuration for this
                        # publisher, only store non-system publisher changes
                        repo = p.repository
                        sticky = p.sticky
                        user_origins = [o for o in repo.origins if not o.system]
                        user_mirrors = [o for o in repo.mirrors if not o.system]
                        old_origins = []
                        old_mirrors = []

                        # look for any previously set configuration
                        if p.prefix in self.img_cfg.publishers:
                                old_pub = self.img_cfg.publishers[p.prefix]
                                old_origins = old_pub.repository.origins
                                old_mirrors = old_pub.repository.mirrors
                                sticky = old_pub.sticky

                        # no user changes, so nothing new to write
                        if set(user_origins) == set(old_origins) and \
                            set(user_mirrors) == set(old_mirrors):
                                continue

                        # store a publisher with this configuration
                        user_pub = publisher.Publisher(prefix=p.prefix,
                            sticky=sticky)
                        user_pub.repository = publisher.Repository()
                        user_pub.repository.origins = user_origins
                        user_pub.repository.mirrors = user_mirrors
                        self.img_cfg.publishers[p.prefix] = user_pub

                # Write out the image configuration.
                self.img_cfg.write()

        def allowed_to_move(self, pub):
                """Return whether a publisher is allowed to move in the search
                order."""

                return not self.__is_sys_pub(pub)

        def add_property_value(self, *args, **kwargs):
                return self.img_cfg.add_property_value(*args, **kwargs)

        def remove_property_value(self, *args, **kwargs):
                return self.img_cfg.remove_property_value(*args, **kwargs)

        def get_index(self):
                return self.img_cfg.get_index()

        def get_policy(self, *args, **kwargs):
                return self.img_cfg.get_policy(*args, **kwargs)

        def get_policy_str(self, *args, **kwargs):
                return self.img_cfg.get_policy_str(*args, **kwargs)

        def get_property(self, section, name):
                # If the property being retrieved is the publisher search order,
                # it's necessary to merge the information from the image
                # configuration and the system configuration.
                if section == "property" and name == "publisher-search-order":
                        res = self.sys_cfg.get_property(section, name)
                        enabled_sys_pubs = [
                            p for p in res
                            if not self.sys_cfg.publishers[p].disabled
                        ]
                        img_pubs = [
                            s for s in self.img_cfg.get_property(section, name)
                            if s not in enabled_sys_pubs
                        ]
                        disabled_sys_pubs = [
                            p for p in res
                            if self.sys_cfg.publishers[p].disabled and \
                                p not in img_pubs
                        ]
                        return enabled_sys_pubs + img_pubs + disabled_sys_pubs
                return self.img_cfg.get_property(section, name)

        def remove_property(self, *args, **kwargs):
                return self.img_cfg.remove_property(*args, **kwargs)

        def set_property(self, *args, **kwargs):
                return self.img_cfg.set_property(*args, **kwargs)

        def set_properties(self, *args, **kwargs):
                return self.img_cfg.set_properties(*args, **kwargs)

        @property
        def target(self):
                return self.img_cfg.target

        @property
        def variants(self):
                return self.img_cfg.variants

        def __get_mediators(self):
                return self.img_cfg.mediators

        def __set_mediators(self, mediators):
                self.img_cfg.mediators = mediators

        mediators = property(__get_mediators, __set_mediators)

        def __get_facets(self):
                return self.img_cfg.facets

        def __set_facets(self, facets):
                self.img_cfg.facets = facets

        facets = property(__get_facets, __set_facets)

        def __get_linked_children(self):
                return self.img_cfg.linked_children

        def __set_linked_children(self, linked_children):
                self.img_cfg.linked_children = linked_children

        linked_children = property(__get_linked_children,
            __set_linked_children)

        def __is_sys_pub(self, prefix):
                """Return whether the publisher with the prefix 'prefix' is a
                system publisher."""

                return prefix in self.sys_cfg.publishers

        def remove_publisher(self, prefix):
                try:
                        del self.publishers[prefix]
                except KeyError:
                        pass

        def change_publisher_search_order(self, being_moved, staying_put,
            after):
                """Change the publisher search order by moving the publisher
                'being_moved' relative to the publisher 'staying put.'  The
                boolean 'after' determines whether 'being_moved' is placed before
                or after 'staying_put'."""

                if being_moved == staying_put:
                        raise apx.MoveRelativeToSelf()

                if self.__is_sys_pub(being_moved):
                        raise apx.ModifyingSyspubException(_("Publisher '%s' "
                            "is a system publisher and cannot be moved.") %
                            being_moved)
                if self.__is_sys_pub(staying_put):
                        raise apx.ModifyingSyspubException(_("Publisher '%s' "
                            "is a system publisher and other publishers cannot "
                            "be moved relative to it.") % staying_put)
                self.img_cfg.change_publisher_search_order(being_moved,
                    staying_put, after)

        def reset(self, overrides=misc.EmptyDict):
                """Discards current configuration state and returns the
                configuration object to its initial state.

                'overrides' is an optional dictionary of property values indexed
                by section name and property name.  If provided, it will be used
                to override any default values initially assigned during reset.
                """

                self.img_cfg.reset(overrides)
                self.sys_cfg.reset()
                old_sysconfig = ImageConfig(os.path.join(imgdir, "pkg5.syspub"),
                    None)
                self.__publishers = self.__merge_publishers(self.img_cfg,
                    self.sys_cfg, self.__pkg_counts, old_sysconfig)

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
                if self.__is_sys_pub(prefix):
                        raise apx.ModifyingSyspubException(_("%s is a system "
                            "publisher and cannot be unset.") % prefix)

                del self.img_cfg.publishers[prefix]
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

        # properties so we can enforce rules and manage two potentially
        # overlapping sets of publishers
        publishers = DictProperty(__get_publisher, __set_publisher,
            __del_publisher, __publisher_iteritems, __publisher_keys,
            __publisher_values, __publisher_iter,
            doc="A dict mapping publisher prefixes to publisher objects")
