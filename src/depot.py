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
import getopt
import os
import re
import sha
import shutil
import time
import urllib

import pkg.catalog as catalog
import pkg.content as content
import pkg.dependency as dependency
import pkg.fmri as fmri
import pkg.package as package
import pkg.version as version

import pkg.server.config as config
import pkg.server.transaction as trans

def usage():
        print """\
Usage: /usr/lib/pkg.depotd [-n]
"""

def catalog(scfg, request):
        scfg.inc_catalog()

        request.send_response(200)
        request.send_header('Content-type', 'text/plain')
        request.end_headers()
        request.wfile.write("%s" % scfg.catalog)

def manifest(scfg, request):
        """The request is an encoded pkg FMRI.  If the version is specified
        incompletely, we return the latest matching manifest.  The matched
        version is returned in the headers.  If an incomplete FMRI is received,
        the client is expected to have provided a build release in the request
        headers.

        Legitimate requests are

        /manifest/[URL]
        /manifest/branch/[URL]
        /manifest/release/[URL]

        allowing the request of the next matching version, based on client
        constraints."""

        scfg.inc_manifest()

        constraint = None

        # Parse request into FMRI component and decode.
        m = re.match("^/manifest/(.*)", request.path)
        pfmri = urllib.unquote(m.group(1))

        # Match package stem.
        f = fmri.PkgFmri(pfmri, None)

        # Determine closest version.
        vs = scfg.catalog.matching_pkgs(f, constraint)

        msg = "Request for %s: " % pfmri
        for v in vs:
                msg = msg + "%s " % v

        request.log_message(msg)

        # Open manifest and send.
        # file = open("%s/%s/%s", scfg.pkg_root, pkgname, pkgversion)
        # data = file.read()

        request.send_response(200)
        request.send_header('Content-type', 'text/plain')
        request.end_headers()
        # request.wfile.write(data)

def get_file(scfg, request):
        """The request is the SHA-1 hash name for the file."""
        scfg.inc_file()

        m = re.match("^/file/(.*)", request.path)
        fhash = m.group(1)

        file = open(scfg.file_root + "/" + fhash)
        data = file.read()

        request.send_response(200)
        request.send_header("Content-type", "application/data")
        request.end_headers()
        request.wfile.write(data)

def trans_open(scfg, request):
        # XXX Authentication will be handled by virtue of possessing a signed
        # certificate (or a more elaborate system).
        t = trans.Transaction()

        ret = t.open(scfg, request)
        if ret == 200:
                scfg.in_flight_trans[t.get_basename()] = t

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
        t = scfg.in_flight_trans[trans_id]
        t.close(request)
        del scfg.in_flight_trans[trans_id]

def trans_abandon(scfg, request):
        # Pull transaction ID from headers.
        m = re.match("^/abandon/(.*)", request.path)
        trans_id = m.group(1)

        t = scfg.in_flight_trans[trans_id]
        t.abandon(request)
        del scfg.in_flight_trans[trans_id]

def trans_add(scfg, request):
        m = re.match("^/add/([^/]*)/(.*)", request.path)
        trans_id = m.group(1)
        type = m.group(2)

        t = scfg.in_flight_trans[trans_id]
        t.add_content(request, type)

if "PKG_REPO" in os.environ:
        scfg = config.SvrConfig(os.environ["PKG_REPO"], "pkg.sun.com")
else:
        scfg = config.SvrConfig("/var/pkg/repo", "pkg.sun.com")

class pkgHandler(BaseHTTPServer.BaseHTTPRequestHandler):

        def do_GET(self):
                # Client APIs
                if re.match("^/catalog$", self.path):
                        catalog(scfg, self)
                elif re.match("^/manifest/.*$", self.path):
                        manifest(scfg, self)
                elif re.match("^/file/.*$", self.path):
                        get_file(scfg, self)

                # Publisher APIs
                elif re.match("^/open/(.*)$", self.path):
                        trans_open(scfg, self)
                elif re.match("^/close/(.*)$", self.path):
                        trans_close(scfg, self)
                elif re.match("^/abandon/(.*)$", self.path):
                        trans_abandon(scfg, self)
                elif re.match("^/add/(.*)$", self.path):
                        trans_add(scfg, self)

                # Informational APIs
                elif re.match("^/$", self.path) or re.match("^/index.html",
                    self.path):
                        self.send_response(200)
                        self.send_header('Content-type', 'text/html')
                        self.end_headers()
                        self.wfile.write("""\
<html>
<body>
<h1><code>pkg</code> server ok</h1>
<h2>Statistics</h2>
<pre>
""")
                        self.wfile.write(scfg.get_status())
                        self.wfile.write("""\
</pre>
<h2>Catalog</h2>
<pre>
""")
                        self.wfile.write("%s" % scfg.catalog)
                        self.wfile.write("""\
</pre>
</body>
</html>""")
                else:
                        self.send_response(404)
                        self.send_header('Content-type', 'text/plain')
                        self.end_headers()
                        self.wfile.write('''404 GET URI %s ; headers %s''' %
                            (self.path, self.headers))


        def do_PUT(self):
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write('''PUT URI %s ; headers %s''' %
                    (self.path, self.headers))

        def do_POST(self):
                if re.match("^/add/(.*)$", self.path):
                        trans_add(scfg, self)
                else:
                        self.send_response(404)

        def do_DELETE(self):
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write('''URI %s ; headers %s''' %
                    (self.path, self.headers))

if __name__ == "__main__":
        scfg.init_dirs()
        scfg.acquire_in_flight()
        scfg.acquire_catalog()

        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "n")
                for opt, arg in opts:
                        if opt == "-n":
                                sys.exit(0)
        except:
                print "pkg.depotd: unknown option"
                usage()

        server = BaseHTTPServer.HTTPServer(('', 10000), pkgHandler)
        server.serve_forever()
