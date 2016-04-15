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
# Copyright (c) 2011, 2016, Oracle and/or its affiliates. All rights reserved.
#

import copy
import os
import simplejson as json
from six.moves.urllib.parse import urlparse, urlunparse

import pkg.client.api_errors as api_errors
import pkg.client.publisher as publisher
import pkg.digest as digest
import pkg.fmri as fmri
from pkg.client.imageconfig import DEF_TOKEN
from pkg.misc import force_bytes

CURRENT_VERSION = 0

def parse(proxy_host, data):
        """Reads the pkg(5) publisher JSON formatted data at 'location'
        or from the provided file-like object 'fileobj' and returns a
        tuple.  The first element of the tuple is a list of publisher objects.
        The second element is a dictionary of image properties.

        'proxy_host' is the string to replace the special string
        'http://<sysrepo>' with when it starts any uri.

        'data' is a string containing the p5s data.
        """

        def transform_urls(urls):
                res = []
                for val in urls:
                        # If the URI contains <sysrepo> then it's served
                        # directly by the system-repository.
                        if val.startswith("http://{0}".format(
                            publisher.SYSREPO_PROXY)):
                                scheme, netloc, path, params, query, fragment =\
                                    urlparse(val)
                                r = publisher.RepositoryURI(
                                        urlunparse((scheme, proxy_host,
                                        path, params, query, fragment)))
                        else:
                                # This URI needs to be proxied through the
                                # system-repository, so we assign it a special
                                # ProxyURI, which gets replaced by the actual
                                # URI of the system-repository in
                                # imageconfig.BlendedConfig.__merge_publishers
                                r = publisher.RepositoryURI(val)
                                r.proxies = [publisher.ProxyURI(None,
                                    system=True)]
                        res.append(r)
                return res

        try:
                dump_struct = json.loads(data)
        except ValueError as e:
                # Not a valid JSON file.
                raise api_errors.InvalidP5SFile(e)

        try:
                ver = int(dump_struct["version"])
        except KeyError:
                raise api_errors.InvalidP5SFile(_("missing version"))
        except ValueError:
                raise api_errors.InvalidP5SFile(_("invalid version"))

        if ver > CURRENT_VERSION:
                raise api_errors.UnsupportedP5SFile()

        pubs = []
        props = {}
        try:
                plist = dump_struct.get("publishers", [])

                # For each set of publisher information in the parsed p5s file,
                # build a Publisher object.
                for p in plist:
                        alias = p.get("alias", None)
                        prefix = p.get("name", None)
                        sticky = p.get("sticky", True)

                        if not prefix:
                                prefix = "Unknown"

                        pub = publisher.Publisher(prefix, alias=alias,
                            sticky=sticky)
                        v = p.get("signature-policy")
                        if v is not None:
                                pub.properties["signature-policy"] = v
                        v = p.get("signature-required-names")
                        if v is not None:
                                pub.properties["signature-required-names"] = v

                        r = p.get("repository", None)
                        if r:
                                rargs = {}
                                for prop in ("collection_type",
                                    "description", "name",
                                    "refresh_seconds", "sticky"):
                                        val = r.get(prop, None)
                                        if val is None or val == "None":
                                                continue
                                        rargs[prop] = val

                                for prop in ("legal_uris", "related_uris"):
                                        val = r.get(prop, [])
                                        if not isinstance(val, list):
                                                continue
                                        rargs[prop] = val

                                for prop in ("mirrors", "origins"):
                                        urls = r.get(prop, [])
                                        if not isinstance(urls, list):
                                                continue
                                        rargs[prop] = transform_urls(urls)
                                repo = publisher.Repository(**rargs)
                                pub.repository = repo
                        pubs.append(pub)

                props["publisher-search-order"] = \
                    dump_struct["image_properties"]["publisher-search-order"]

                sig_pol = dump_struct["image_properties"].get(
                    "signature-policy")
                if sig_pol is not None:
                        props["signature-policy"] = sig_pol

                req_names = dump_struct["image_properties"].get(
                    "signature-required-names")
                if req_names is not None:
                        props["signature-required-names"] = req_names
        except (api_errors.PublisherError, TypeError, ValueError) as e:
                raise api_errors.InvalidP5SFile(str(e))
        return pubs, props

def write(fileobj, pubs, cfg):
        """Writes the publisher, repository, and provided package names to the
        provided file-like object 'fileobj' in JSON p5i format.

        'fileobj' is an object that has a 'write' method that accepts data to be
        written as a parameter.

        'pubs' is a list of Publisher objects.

        'cfg' is an ImageConfig which contains the properties of the image on
        which the generated p5s file is based."""

        def transform_uris(urls, prefix):
                res = []

                for u in urls:
                        m = copy.copy(u)
                        if m.scheme == "http":
                                res.append(m.uri)
                        elif m.scheme == "https":
                                # The system depot handles connecting to the
                                # proxied https repositories, so the client
                                # should communicate over http to prevent it
                                # from doing tunneling.
                                m.change_scheme("http")
                                res.append(m.uri)
                        elif m.scheme == "file":
                                # The system depot provides direct access to
                                # file repositories.  The token <sysrepo> will
                                # be replaced in the client with the url it uses
                                # to communicate with the system repository.
                                res.append("http://{0}/{1}/{2}".format(
                                    publisher.SYSREPO_PROXY, prefix,
                                    digest.DEFAULT_HASH_FUNC(
                                    force_bytes(m.uri.rstrip("/"))).hexdigest()
                                    ))
                        else:
                                assert False, "{0} is an unknown scheme.".format(
                                    u.scheme)

                # Remove duplicates, since the system-repository can only
                # provide one path to a given origin. This can happen if the
                # image has eg. two origins/mirrors configured for a publisher,
                # with one using http and the other using https, but both using
                # the same netloc and path.
                # We want to preserve origin/mirror order, so simply casting
                # into a set is not appropriate.
                values = set()
                res_unique = []
                for item in res:
                        if item not in values:
                                values.add(item)
                                res_unique.append(item)
                return res_unique

        dump_struct = {
            "publishers": [],
            "image_properties": {},
            "version": CURRENT_VERSION,
        }

        dpubs = dump_struct["publishers"]
        prefixes = set()
        for p in pubs:

                d = None
                if p.repository:
                        r = p.repository
                        reg_uri = ""

                        mirrors = transform_uris(r.mirrors, p.prefix)
                        origins = transform_uris(r.origins, p.prefix)
                        d = {
                            "collection_type": r.collection_type,
                            "description": r.description,
                            "legal_uris": [u.uri for u in r.legal_uris],
                            "mirrors": mirrors,
                            "name": r.name,
                            "origins": origins,
                            "refresh_seconds": r.refresh_seconds,
                            "related_uris": [
                                u.uri for u in r.related_uris
                            ],
                        }

                dpub = {
                    "alias": p.alias,
                    "name": p.prefix,
                    "repository": d,
                    "sticky": p.sticky,
                }

                sp = p.properties.get("signature-policy")
                if sp and sp != DEF_TOKEN:
                    dpub["signature-policy"] = sp

                srn = p.properties.get("signature-required-names")
                if srn:
                    dpub["signature-required-names"] = \
                        p.properties["signature-required-names"]

                dpubs.append(dpub)
                prefixes.add(p.prefix)

        dump_struct["image_properties"]["publisher-search-order"] = [
            p for p in cfg.get_property("property", "publisher-search-order")
            if p in prefixes
        ]

        sig_pol = cfg.get_property("property", "signature-policy")
        if sig_pol != DEF_TOKEN:
                dump_struct["image_properties"]["signature-policy"] = sig_pol

        req_names = cfg.get_property("property", "signature-required-names")
        if req_names:
                dump_struct["image_properties"]["signature-required-names"] = \
                    req_names

        json.dump(dump_struct, fileobj, ensure_ascii=False,
            allow_nan=False, indent=2, sort_keys=True)
        fileobj.write("\n")
