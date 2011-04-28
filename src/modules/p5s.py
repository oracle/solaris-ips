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
# Copyright (c) 2011, Oracle and/or its affiliates. All rights reserved.
#

import copy
import hashlib
import os
import pkg.client.api_errors as api_errors
import pkg.client.publisher as publisher
import pkg.fmri as fmri
import simplejson as json
import urllib
import urllib2
import urlparse

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
                        # If the url is an http url, then we need to proxy it
                        # through the system repository.
                        if val.startswith("http://<sysrepo>"):
                                scheme, netloc, path, params, query, fragment =\
                                    urlparse.urlparse(val)
                                val = urlparse.urlunparse((scheme, proxy_host,
                                    path, params, query, fragment))
                        res.append(val)
                return res
        
        try:
                dump_struct = json.loads(data)
        except ValueError, e:
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
                        pub.properties["proxied-urls"] = \
                            p.get("proxied-urls", [])

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
        except (api_errors.PublisherError, TypeError, ValueError), e:
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
                proxied = []

                for u in urls:
                        m = copy.copy(u)
                        if m.scheme == "http":
                                res.append(m.uri)
                                proxied.append(m.uri)
                        elif m.scheme == "https":
                                # The system depot handles connecting to the
                                # proxied https repositories, so the client
                                # should communicate over http to prevent it
                                # from doing tunneling.
                                m.change_scheme("http")
                                res.append(m.uri)
                                proxied.append(m.uri)
                        elif m.scheme == "file":
                                # The system depot provides direct access to
                                # file repositories.  The token <sysrepo> will
                                # be replaced in the client with the url it uses
                                # to communicate with the system repository.
                                res.append("http://<sysrepo>/%s/%s" %
                                    (prefix,
                                    hashlib.sha1(m.uri.rstrip("/")).hexdigest()
                                    ))
                        else:
                                assert False, "%s is an unknown scheme." % \
                                    u.scheme
                return res, proxied

        dump_struct = {
            "publishers": [],
            "image_properties": {},
            "version": CURRENT_VERSION,
        }

        dpubs = dump_struct["publishers"]
        prefixes = set()
        for p in pubs:

                d = None
                proxied_urls = []
                if p.repository:
                        r = p.repository
                        reg_uri = ""

                        mirrors, t = transform_uris(r.mirrors, p.prefix)
                        proxied_urls.extend(t)
                        origins, t = transform_uris(r.origins, p.prefix)
                        proxied_urls.extend(t)
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
                    "proxied-urls" : proxied_urls,
                    "repository": d,
                    "sticky": p.sticky,
                }
                dpubs.append(dpub)
                prefixes.add(p.prefix)

        dump_struct["image_properties"]["publisher-search-order"] = [
            p for p in cfg.get_property("property", "publisher-search-order")
            if p in prefixes
        ]

        json.dump(dump_struct, fileobj, ensure_ascii=False,
            allow_nan=False, indent=2, sort_keys=True)
        fileobj.write("\n")
