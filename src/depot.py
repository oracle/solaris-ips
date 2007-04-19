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

# pkg.depotd - package repository daemon

import BaseHTTPServer
import os
import re
import sha
import shutil
import time
import urllib

import pkg.catalog as catalog
import pkg.config as config
import pkg.content as content
import pkg.dependency as dependency
import pkg.fmri as fmri
import pkg.image as image
import pkg.package as package
import pkg.transaction as trans
import pkg.version as version

# in_flight_trans needs to be rebuilt on restart
in_flight_trans = {}

def catalog(scfg, request):
        """The marshalled form of the catalog is

        pkg_name (release (branch (sequence ...) ...) ...)

        since we know that the server is only to report packages for which it
        can offer a record.
        """

        request.send_response(200)
        request.send_header('Content-type:', 'text/plain')
        request.end_headers()
        request.wfile.write('''GET URI %s ; headers %s''' % (request.path, request.headers))

def trans_open(scfg, request):
        # XXX Authentication will be handled by virtue of possessing a signed
        # certificate (or a more elaborate system).
        t = trans.Transaction()

        ret = t.open(scfg, request)
        if ret == 200:
                in_flight_trans[t.get_basename()] = t

                request.send_response(200)
                request.send_header('Content-type', 'text/plain')
                request.send_header('Transaction-ID', t.get_basename())
                request.end_headers()
        elif ret == 400:
                request.send_response(400)
        else:
                request.send_response(500)


def trans_close(scfg, request):
        # Pull transaction ID from headers.
        m = re.match("^/close/(.*)", request.path)
        trans_id = m.group(1)

        # XXX KeyError?
        t = in_flight_trans[trans_id]
        t.close(request)
        del in_flight_trans[trans_id]

def trans_abandon(scfg, request):
        # Pull transaction ID from headers.
        m = re.match("^/abandon/(.*)", request.path)
        trans_id = m.group(1)

        t = in_flight_trans[trans_id]
        t.abandon(request)
        del in_flight_trans[trans_id]

def trans_add(scfg, request):
        m = re.match("^/add/([^/]*)/(.*)", request.path)
        trans_id = m.group(1)
        type = m.group(2)

        t = in_flight_trans[trans_id]
        t.add_content(request, type)

if "PKG_REPO" in os.environ:
        scfg = config.SvrConfig(os.environ["PKG_REPO"])
else:
        scfg = config.SvrConfig("/var/pkg/repo")

class pkgHandler(BaseHTTPServer.BaseHTTPRequestHandler):

        def do_GET(self):
                if re.match("^/catalog$", self.path):
                        catalog(scfg, self)
                elif re.match("^/open/(.*)$", self.path):
                        trans_open(scfg, self)
                elif re.match("^/close/(.*)$", self.path):
                        trans_close(scfg, self)
                elif re.match("^/abandon/(.*)$", self.path):
                        trans_abandon(scfg, self)
                elif re.match("^/add/(.*)$", self.path):
                        trans_add(scfg, self)
                elif re.match("^/$", self.path) or re.match("^/index.html", self.path):
                        self.send_response(200)
                        self.send_header('Content-type', 'text/html')
                        self.end_headers()
                        self.wfile.write("""<html><body><h1><code>pkg</code> server ok</h1>\n""")
                        self.wfile.write("""</body></html>""")
                else:
                        self.send_response(404)
                        self.send_header('Content-type', 'text/plain')
                        self.end_headers()
                        self.wfile.write('''404 GET URI %s ; headers %s''' % (self.path, self.headers))


        def do_PUT(self):
                self.send_response(200)
                self.send_header('Content-type:', 'text/plain')
                self.end_headers()
                self.wfile.write('''PUT URI %s ; headers %s''' % (self.path, self.headers))

        def do_POST(self):
                if re.match("^/add/(.*)$", self.path):
                        trans_add(scfg, self)
                else:
                        self.send_response(404)

        def do_DELETE(self):
                self.send_response(200)
                self.send_header('Content-type:', 'text/plain')
                self.end_headers()
                self.wfile.write('''URI %s ; headers %s''' % (self.path, self.headers))

if __name__ == "__main__":
        scfg.init_dirs()
        server = BaseHTTPServer.HTTPServer(('', 10000), pkgHandler)
        server.serve_forever()
