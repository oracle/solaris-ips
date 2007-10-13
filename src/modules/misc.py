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
# Copyright 2007 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import os
import urllib
import urllib2
import urlparse

def hash_file_name(f):
        """Return the two-level path fragment for the given filename, which is
        assumed to be a content hash of at least 8 distinct characters."""
        return os.path.join("%s" % f[0:2], "%s" % f[2:8], "%s" % f)

def versioned_urlopen(base_uri, operation, versions = [], tail = None,
    data = None, headers = {}):
        """Open the best URI for an operation given a set of versions.

        Both the client and the server may support multiple versions of
        the protocol of a particular operation.  The client will pass
        this method an ordered array of versions it understands, along
        with the base URI and the operation it wants.  This method will
        open the URL corresponding to the best version both the client
        and the server understand, returning a tuple of the open URL and
        the version used on success, and throwing an exception if no
        matching version can be found.
        """
        # Ignore http_proxy for localhost case, by overriding
        # default proxy behaviour of urlopen().
        netloc = urlparse.urlparse(base_uri)[1]
        if urllib.splitport(netloc)[0] == "localhost":
                # XXX cache this opener?
                proxy_handler = urllib2.ProxyHandler({})
                opener_dir = urllib2.build_opener(proxy_handler)
                url_opener = opener_dir.open
        else:
                url_opener = urllib2.urlopen

        for version in versions:
                if tail:
                        uri = urlparse.urljoin(base_uri, "%s/%s/%s" % \
                            (operation, version, tail))
                else:
                        uri = urlparse.urljoin(base_uri, "%s/%s" % \
                            (operation, version))

                req = urllib2.Request(url = uri, headers = headers)
                if data is not None:
                        req.add_data(data)

                try:
                        c = url_opener(req)
                except urllib2.URLError, e:
                        if e.code != 404 or e.msg != "Version not supported":
                                raise
                        continue
                # XXX catch BadStatusLine and convert to 500?

                return c, version
        else:
                # Couldn't find a version that we liked.
                raise RuntimeError, \
                    "%s doesn't speak a known version of %s operation" % \
                    (base_uri, operation)

if __name__ == "__main__":
        print hash_file_name("abcdefghijklmnopqrstuvwxyz")
