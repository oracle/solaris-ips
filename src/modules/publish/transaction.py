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
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

# We use urllib2 for GET and POST operations, but httplib for PUT and DELETE
# operations.

import httplib
import os
import urllib
import urllib2

from pkg.misc import versioned_urlopen
import pkg.portable.util as os_util

class Transaction(object):

        def __init__(self):
                self.cfg = None
                self.pkg_name = ""
                return

        # XXX This opens a Transaction, but who manages the server connection?
        # If we want a pipelined HTTP session (multiple operations -- even if
        # it's only one Transaction -- over a single connection), then we can't
        # call HTTPConnection.close() here, and we shouldn't reopen the
        # connection in Transaction.add(), Transaction.close(), etc.
        def open(self, config, pkg_name):
                self.cfg = config
                self.pkg_name = pkg_name

                try:
                        c, v = versioned_urlopen(self.cfg.install_uri, "open",
                            [0], urllib.quote(self.pkg_name, ""),
                            headers = {"Client-Release": os_util.get_os_release()})
                except (httplib.BadStatusLine, RuntimeError):
                        return httplib.INTERNAL_SERVER_ERROR, None
                except urllib2.HTTPError, e:
                        return e.code, None

                id = c.headers.get("Transaction-ID", None)

                return c.code, id

        # XXX shouldn't need to pass trans_id or config in, as it ought to
        # be part of self.  But currently, the front-end is stateless
        # across individual transaction elements, so we need to carry this
        # around.
        def close(self, config, trans_id, abandon=False):
                op = "close"
                if abandon:
                        op = "abandon"

                repo = config.install_uri
                try:
                        c, v = versioned_urlopen(repo, op, [0], trans_id)
                except (httplib.BadStatusLine, RuntimeError):
                        return httplib.INTERNAL_SERVER_ERROR, None
                except urllib2.HTTPError, e:
                        return e.code, None

                if abandon:
                        return c.code, None

                # Return only the headers the client should care about.
                # XXX is there any reason to try/except KeyError here?
                ret_hdrs = ["State", "Package-FMRI"]
                return c.code, dict((h, c.info()[h]) for h in ret_hdrs)

        def add(self, config, trans_id, action):
                """POST the file contents to the transaction."""

                type = action.name
                attrs = action.attrs

                # XXX Need to handle large files
                if action.data != None:
                        datastream = action.data()
                        data = datastream.read()
                else:
                        data = ""

                headers = dict(
                    ("X-IPkg-SetAttr%s" % i, "%s=%s" % (k, attrs[k]))
                    for i, k in enumerate(attrs)
                )
                headers["Content-Length"] = len(data)

                try:
                        c, v = versioned_urlopen(config.install_uri, "add",
                            [0], "%s/%s" % (trans_id, type), data = data,
                            headers = headers)
                except httplib.BadStatusLine:
                        return httplib.INTERNAL_SERVER_ERROR, "Bad status line from server", None
                except RuntimeError, e:
                        return httplib.NOT_FOUND, e[0], None
                except urllib2.HTTPError, e:
                        return e.code, e.msg, None
                except urllib2.URLError, e:
                        if e.reason[0] == 32: # Broken pipe
                                # XXX Guess: the libraries don't ever collect
                                # this information.  This might also be "Version
                                # not supported".
                                return httplib.NOT_FOUND, "Transaction ID not found", None
                        else:
                                return httplib.INTERNAL_SERVER_ERROR, e.reason[1], None

                return c.code, c.msg, None

        def rename(self, config, src_fmri, dest_fmri):
                """Issue a POST to rename src_fmri to dest_fmri."""

                req_dict = { 'Src-FMRI': src_fmri, 'Dest-FMRI': dest_fmri }

                req_str = urllib.urlencode(req_dict)

                try:
                        c, v = versioned_urlopen(config.install_uri, "rename",
                            [0], data = req_str)
                except httplib.BadStatusLine:
                        return httplib.INTERNAL_SERVER_ERROR, "Bad status line from server", None
                except RuntimeError, e:
                        return httplib.NOT_FOUND, e[0], None
                except urllib2.HTTPError, e:
                        return e.code, e.msg, None
                except urllib2.URLError, e:
                        if e.reason[0] == 32: # Broken pipe
                                # XXX Guess: the libraries don't ever collect
                                # this information.
                                return httplib.NOT_FOUND, "Version not supported", None
                        else:
                                return httplib.INTERNAL_SERVER_ERROR, e.reason[1], None

                return c.code, c.msg, None

