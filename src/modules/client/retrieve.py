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
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import socket
import urllib2

from pkg.misc import versioned_urlopen

# client/retrieve.py - collected methods for retrieval of pkg components
# from repositories

def get_datastream(img, fmri, hash):
        """Retrieve a file handle based on a package fmri and a file hash."""

        authority, pkg_name, version = fmri.tuple()

        url_prefix = img.get_url_by_authority(authority)
        ssl_tuple = img.get_ssl_credentials(authority)

        try:
                f, v = versioned_urlopen(url_prefix, "file", [0], hash,
                           ssl_creds = ssl_tuple, imgtype = img.type)
        except urllib2.URLError, e:
                if len(e.args) == 1 and isinstance(e.args[0], socket.sslerror):
                        raise RuntimeError, e

                raise NameError, "could not retrieve file '%s' from '%s'" % \
                    (hash, url_prefix)
        except:
                raise NameError, "could not retrieve file '%s' from '%s'" % \
                    (hash, url_prefix)

        return f

def get_manifest(img, fmri):
        """ Calculate URI and retrieve manifest.  Return it as a buffer to
            the caller. """

        authority, pkg_name, version = fmri.tuple()

        url_prefix = img.get_url_by_authority(authority)
        ssl_tuple = img.get_ssl_credentials(authority)

        try:
                m, v = versioned_urlopen(url_prefix, "manifest", [0],
                    fmri.get_url_path(), ssl_creds = ssl_tuple,
                    imgtype = img.type)
        except urllib2.URLError, e:
                if len(e.args) == 1 and isinstance(e.args[0], socket.sslerror):
                        raise RuntimeError, e

                raise NameError, "could not retrieve manifest '%s' from '%s'" % \
                    (hash, url_prefix)
        except:
                raise NameError, "could not retrieve manifest '%s' from '%s'" % \
                    (fmri.get_url_path(), url_prefix)

        return m.read()
