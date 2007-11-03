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

import os
import sys
import urllib
import urlparse

from pkg.misc import versioned_urlopen

# client/retrieve.py - collected methods for retrieval of pkg components
# from repositories

def get_datastream(img, fmri, hash):
        """Retrieve a file handle based on a package fmri and a file hash."""

        authority, pkg_name, version = fmri.tuple()

        url_prefix = img.get_url_by_authority(authority)

        try:
                f, v = versioned_urlopen(url_prefix, "file", [0], hash)
        except:
                raise NameError, "could not retrieve file '%s' from '%s'" % \
                    (hash, url_prefix)

        return f

def get_manifest(img, fmri):
        """Calculate URI and retrieve."""

        authority, pkg_name, version = fmri.tuple()

        url_prefix = img.get_url_by_authority(authority)

        try:
                m, v = versioned_urlopen(url_prefix, "manifest", [0],
                    fmri.get_url_path())
        except:
                raise NameError, "could not retrieve manifest '%s' from '%s'" % \
                    (fmri.get_url_path(), url_prefix)

        data = m.read()
        local_mpath = "%s/pkg/%s/manifest" % (img.imgdir, fmri.get_dir_path())

        try:
                mfile = file(local_mpath, "w")
                print >>mfile, data
        except IOError, e:
                os.makedirs(os.path.dirname(local_mpath))
                mfile = file(local_mpath, "w")
                print >>mfile, data
