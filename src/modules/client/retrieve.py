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
#

import getopt
import httplib
import os
import re
import sys
import urllib
import urllib2
import urlparse

# client/retrieve.py - collected methods for retrieval of pkg components
# from repositories

def url_catalog(config, image, args):
        """XXX will need to show available content series for each package"""
        croot = image.imgdir

        if len(args) != 0:
                print "pkg: catalog subcommand takes no arguments"
                usage()

        # Ensure Image directory structure is valid.
        if not os.path.isdir("%s/catalog" % croot):
                image.mkdirs()

        # GET /catalog
        for repo in pcfg.repo_uris:
                # Ignore http_proxy for localhost case, by overriding default
                # proxy behaviour of urlopen().
                proxy_uri = None
                netloc = urlparse.urlparse(repo)[1]
                if urllib.splitport(netloc)[0] == "localhost":
                        proxy_uri = {}

                uri = urlparse.urljoin(repo, "catalog")

                c = urllib.urlopen(uri, proxies=proxy_uri)

                # compare headers
                data = c.read()
                fname = urllib.quote(c.geturl(), "")

                # Filename should be reduced to host\:port
                cfile = file("%s/catalog/%s" % (croot, fname), "w")
                print >>cfile, data

def get_datastream(fmri, hash):
        """Retrieve a file handle based on a package fmri and a file hash."""

        authority, pkg_name, version = fmri.tuple()

        if authority == None:
                authority = "localhost:10000"

        url_fpath = "http://%s/file/%s" % (authority, hash)

        try:
                f = urllib.urlopen(url_fpath)
        except:
                raise NameError, "could not open %s" % url_fpath

        return f

def get_manifest(image, fmri):
        """Calculate URI and retrieve.
        XXX Authority-catalog issues."""

        authority, pkg_name, version = fmri.tuple()

        # XXX convert authority reference to server
        if authority == None:
                authority = "localhost:10000"

        url_mpath = "http://%s/manifest/%s" % (authority,
            fmri.get_url_path())

        try:
                m = urllib.urlopen(url_mpath)
        except:
                raise NameError, "could not open %s" % url_mpath

        data = m.read()
        local_mpath = "%s/pkg/%s/manifest" % (image.imgdir, fmri.get_dir_path())

        try:
                mfile = file(local_mpath, "w")
                print >>mfile, data
        except IOError, e:
                os.makedirs(os.path.dirname(local_mpath))
                mfile = file(local_mpath, "w")
                print >>mfile, data
