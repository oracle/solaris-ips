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


import BaseHTTPServer
import os
import re
import sha
import shutil
import time

import pkg.version as version
import pkg.fmri as fmri
import pkg.catalog as catalog
import pkg.config as config

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
        # mkdir repo_root + "/trans/" + trans_id
        trans_root = "%s/trans" % scfg.repo_root
        # XXX refine try/except
        try:
                os.makedirs(trans_root)
        except OSError:
                pass
        opening_time = time.time()
        m = re.match("^/open/(.*)", request.path)
        pkg_name = m.group(1)

        # XXX opaquify using hash
        trans_basename = "%d_%s" % (opening_time, pkg_name)
        os.makedirs("%s/%s" % (trans_root, trans_basename))

        # record transaction metadata:  opening_time, package, user
        # lookup package by name
        # if not found, create package
        # set package state to TRANSACTING

        request.send_response(200)
        request.send_header('Content-type:', 'text/plain')
        request.end_headers()
        request.wfile.write('Transaction-ID: %s' % trans_basename)

def trans_close(scfg, request):
        # Pull transaction ID from headers.
        m = re.match("^/close/(.*)", request.path)
        trans_id = m.group(1)

        trans_root = "%s/trans" % scfg.repo_root
        # XXX refine try/except
        #
        # set package state to SUBMITTED
        # attempt to reconcile dependencies
        # if reconciled, set state to PUBLISHED
        #   call back to check incomplete list
        # else set state to INCOMPLETE
        try:
                shutil.rmtree("%s/%s" % (trans_root, trans_id))
                request.send_response(200)
        except:
                request.send_response(404)

def trans_add(scfg, request):
        m = re.match("^/add/([^/]*)/(.*)", request.path)
        trans_id = m.group(1)
        type = m.group(2)

        trans_root = "%s/trans" % scfg.repo_root
        # XXX refine try/except
        hdrs = request.headers
        path = hdrs.getheader("Path")

        data = request.rfile.read()
        hash = sha.new(data)
        fname = hash.hexdigest()

        ofile = file("%s/%s/%s" % (trans_root, trans_id, fname), "wb")
        ofile.write(data)

        tfile = file("%s/%s/manifest" % (trans_root, trans_id), "a")
        print >>tfile, "%s %s" % (path, fname)

if "PKG_REPO" in os.environ:
	scfg = SvrConfig(os.environ["PKG_REPO"])
else
	scfg = SvrConfig("/var/pkg/repo")

class pkgHandler(BaseHTTPServer.BaseHTTPRequestHandler):

        def do_GET(self):
                if re.match("^/catalog$", self.path):
                        catalog(scfg, self)
                elif re.match("^/open/(.*)$", self.path):
                        trans_open(scfg, self)
                elif re.match("^/close/(.*)$", self.path):
                        trans_close(scfg, self)
                elif re.match("^/add/(.*)$", self.path):
                        trans_add(scfg, self)
                else:
                        self.send_response(404)


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

server = BaseHTTPServer.HTTPServer(('', 10000), pkgHandler)
server.serve_forever()
