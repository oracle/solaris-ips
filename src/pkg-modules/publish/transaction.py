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
#

import httplib
import os
import urllib
import urllib2
import urlparse

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

                repo = self.cfg.install_uri
                uri_exp = urlparse.urlparse(repo)
                host, port = uri_exp[1].split(":")

                c = httplib.HTTPConnection(host, port)
                c.connect()
                c.putrequest("GET", "/open/%s" %
                        urllib.quote(self.pkg_name, ""))
                c.putheader("Client-Release", os.uname()[2])
                c.endheaders()

                r = c.getresponse()

                id = r.getheader("Transaction-ID", None)

                return r.status, id

        # XXX shouldn't need to pass trans_id or config in, as it ought to
        # be part of self.  But currently, the front-end is stateless
        # across individual transaction elements, so we need to carry this
        # around.
        def close(self, config, trans_id, abandon=False):
                op = "close"
                if abandon:
                        op = "abandon"

                repo = config.install_uri
                uri = urlparse.urljoin(repo, "%s/%s" % (op, trans_id))
                try:
                        c = urllib2.urlopen(uri)
                except urllib2.HTTPError:
                        return 0, None

                if abandon:
                        return c.code, None

                # Return only the headers the client should care about.
                # XXX is there any reason to try/except KeyError here?
                ret_hdrs = ["State", "Package-FMRI"]
                return c.code, dict((h, c.info()[h]) for h in ret_hdrs)

        def add(self, config, trans_id, type="file", **keywords):
                """POST the file contents to the transaction.  Default is to
                post to the currently open content series.  -s option selects a
                different series.

                dir mode owner group path [n=v ...]
                file mode owner group path [n=v ...]
                displace mode owner group path [n=v ...]
                preserve mode owner group path [n=v ...]

                link path_from path_to [n=v ...]
                        This action is exclusively for symbolic links.

                service manifest_path [n=v ...]
                        0444 root sys
                driver class  [n=v ...] (a whole slew of specifiers)
                        0755 root sys binaries; 0644 root sys conf file

                restart fmri [n=v ...]
                        [no file, illegal in user image]

                XXX do we need hardlinks?

                XXX driver action could follow the upload of two or three files.
                In this case, the action can either cause the transaction to
                fail (since modes and ownership may be inconsistent) or correct
                the transaction to follow convention (with a warning).

                XXX driver action must be architecture tag-dependent, as a
                driver may exist only on a single platform kind.

                XXX Setting a driver from the command line, rather than via a
                batched file, seems error prone.

                XXX File types needs to be made a modular API, and not be
                hard-coded."""

                if not type in (
                        "dir",
                        "displace",
                        # "driver",
                        "file",
                        # "hardlink",
                        # "link",
                        "preserve",
                        # "restart",
                        "service"
                ):
                        raise BadTypeException

                repo = config.install_uri
                uri_exp = urlparse.urlparse(repo)
                host, port = uri_exp[1].split(":")
                selector = "/add/%s/%s" % (trans_id, type)

                attributes = {
                        "dir": ("mode", "owner", "group", "path"),
                        "displace": ("mode", "owner", "group", "path"),
                        "file": ("mode", "owner", "group", "path"),
                        "preserve": ("mode", "owner", "group", "path"),
                        "service": ("manifest", ),
                }

                headers = dict((k.capitalize(), keywords[k])
                        for k in keywords if k in attributes[type])

                if type in ("file", "displace", "preserve", "service"):
                        # XXX Need to handle larger files than available swap.
                        file = open(keywords["file"])
                        data = file.read()
                elif type == "dir":
                        data = ""

                c = httplib.HTTPConnection(host, port)
                c.connect()
                c.request("POST", selector, data, headers)

                r = c.getresponse()

                return r.status

        def meta(self, config, trans_id, args):
                """Via POST request, transfer a piece of metadata to the server.

                XXX This is just a stub.
                """

                repo = config.install_uri
                uri_exp = urlparse.urlparse(repo)
                host, port = uri_exp[1].split(":")
                selector = "/meta/%s/%s" % (trans_id, args[0])

                # subcommand handling
                # /meta/trans_id/set/property_name
                #       Payload is value.
                # /meta/trans_id/unset/property_name
                #       No payload.
                # /meta/trans_id/include
                # /meta/trans_id/require
                # /meta/trans_id/exclude
                #       Payload is fmri.
                # /meta/trans_id/disclaim
                #       Payload is fmri.

                headers = {}
                headers["Path"] = args[1]

                c = httplib.HTTPConnection(host, port)
                c.connect()
                c.request("POST", selector, data, headers)
                return
