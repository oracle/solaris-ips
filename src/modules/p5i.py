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

#
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import os
import pkg.client.api_errors as api_errors
import pkg.client.publisher as publisher
import pkg.fmri as fmri
import simplejson as json
import urllib
import urllib2
import urlparse

CURRENT_VERSION = 1
MIME_TYPE = "application/vnd.pkg5.info"

def parse(fileobj=None, location=None):
        """Reads the pkg(5) publisher json formatted data at 'location'
        or from the provided file-like object 'fileobj' and returns a
        list of tuples of the format (publisher object, pkg_names).
        pkg_names is a list of strings representing package names or
        FMRIs.  If any pkg_names not specific to a publisher were
        provided, the last tuple returned will be of the format (None,
        pkg_names).

        'fileobj' is an optional file-like object that must support a
        'read' method for retrieving data.

        'location' is an optional string value that should either start
        with a leading slash and be pathname of a file or a URI string.
        If it is a URI string, supported protocol schemes are 'file',
        'ftp', 'http', and 'https'.

        'fileobj' or 'location' must be provided."""

        if location is None and fileobj is None:
                raise api_errors.InvalidResourceLocation(location)

        if location:
                if location.find("://") == -1:
                        # Convert the file path to a URI.
                        location = os.path.abspath(location)
                        location = urlparse.urlunparse(("file", "",
                            urllib.pathname2url(location), "", "", ""))

                try:
                        fileobj = urllib2.urlopen(location)
                except (EnvironmentError, ValueError,
                    urllib2.HTTPError), e:
                        raise api_errors.RetrievalError(e,
                            location=location)

        try:
                dump_struct = json.load(fileobj)
        except (EnvironmentError, urllib2.HTTPError), e:
                raise api_errors.RetrievalError(e)
        except ValueError, e:
                # Not a valid json file.
                raise api_errors.InvalidP5IFile(e)

        try:
                ver = int(dump_struct["version"])
        except KeyError:
                raise api_errors.InvalidP5IFile(_("missing version"))
        except ValueError:
                raise api_errors.InvalidP5IFile(_("invalid version"))

        if ver > CURRENT_VERSION:
                raise api_errors.UnsupportedP5IFile()

        result = []
        try:
                plist = dump_struct.get("publishers", [])

                for p in plist:
                        alias = p.get("alias", None)
                        prefix = p.get("name", None)

                        if not prefix:
                                prefix = "Unknown"

                        pub = publisher.Publisher(prefix, alias=alias)
                        pkglist = p.get("packages", [])
                        result.append((pub, pkglist))

                        for r in p.get("repositories", []):
                                rargs = {}
                                for prop in ("collection_type",
                                    "description", "name",
                                    "refresh_seconds",
                                    "registration_uri"):
                                        val = r.get(prop, None)
                                        if val is None or val == "None":
                                                continue
                                        rargs[prop] = val

                                for prop in ("legal_uris", "mirrors",
                                    "origins", "related_uris"):
                                        val = r.get(prop, [])
                                        if not isinstance(val, list):
                                                continue
                                        rargs[prop] = val

                                if rargs.get("origins", None):
                                        repo = publisher.Repository(
                                            **rargs)
                                        pub.add_repository(repo)

                pkglist = dump_struct.get("packages", [])
                if pkglist:
                        result.append((None, pkglist))
        except (api_errors.PublisherError, TypeError, ValueError), e:
                raise api_errors.InvalidP5IFile(str(e))
        return result

def write(fileobj, pubs, pkg_names=None):
        """Writes the publisher, repository, and provided package names to the
        provided file-like object 'fileobj' in json p5i format.

        'fileobj' is an object that has a 'write' method that accepts data to be
        written as a parameter.

        'pkg_names' is a dict of lists, tuples, or sets indexed by publisher
        prefix that contain package names, FMRI strings, or FMRI objects.  A
        prefix of "" can be used for packages that are that are not specific to
        a publisher.

        'pubs' is a list of Publisher objects."""

        dump_struct = {
            "packages": [],
            "publishers": [],
            "version": CURRENT_VERSION,
        }

        if pkg_names is None:
                pkg_names = {}

        def copy_pkg_names(source, dest):
                for entry in source:
                        # Publisher information is intentionally
                        # omitted as association with this specific
                        # publisher is implied by location in the
                        # output.
                        if isinstance(entry, fmri.PkgFmri):
                                dest.append(entry.get_fmri(
                                    anarchy=True))
                        else:
                                dest.append(str(entry))

        dpubs = dump_struct["publishers"]
        for p in pubs:
                dpub = {
                    "alias": p.alias,
                    "name": p.prefix,
                    "packages": [],
                    "repositories": []
                }
                dpubs.append(dpub)

                try:
                        copy_pkg_names(pkg_names[p.prefix],
                            dpub["packages"])
                except KeyError:
                        pass

                drepos = dpub["repositories"]
                for r in p.repositories:
                        reg_uri = ""
                        if r.registration_uri:
                                reg_uri = r.registration_uri.uri

                        drepos.append({
                            "collection_type": r.collection_type,
                            "description": r.description,
                            "legal_uris": [u.uri for u in r.legal_uris],
                            "mirrors": [u.uri for u in r.mirrors],
                            "name": r.name,
                            "origins": [u.uri for u in r.origins],
                            "refresh_seconds": r.refresh_seconds,
                            "registration_uri": reg_uri,
                            "related_uris": [
                                u.uri for u in r.related_uris
                            ],
                        })

        try:
                copy_pkg_names(pkg_names[""], dump_struct["packages"])
        except KeyError:
                pass

        json.dump(dump_struct, fileobj, ensure_ascii=False,
            allow_nan=False, indent=2, sort_keys=True)
        fileobj.write("\n")
