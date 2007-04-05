#!/usr/bin/python

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

scfg = SvrConfig("/home/sch/play/pkg/repo")

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
