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

# XXX The prototype pkg.depotd combines both the version management server that
# answers to pkgsend(1) sessions and the HTTP file server that answers to the
# various GET operations that a pkg(1) client makes.  This split is expected to
# be made more explicit, by constraining the pkg(1) operations such that they
# can be served as a typical HTTP/HTTPS session.  Thus, pkg.depotd will reduce
# to a special purpose HTTP/HTTPS server explicitly for the version management
# operations, and must manipulate the various state files--catalogs, in
# particular--such that the pkg(1) pull client can operately accurately with
# only a basic HTTP/HTTPS server in place.

# XXX We should support simple "last-modified" operations via HEAD queries.

# XXX Although we pushed the evaluation of next-version, etc. to the pull
# client, we should probably provide a query API to do same on the server, for
# dumb clients (like a notification service).

import BaseHTTPServer
import SocketServer
import socket
import errno
import getopt
import os
import re
import sys
import urllib
import tarfile
import cgi
import traceback

import pkg.fmri as fmri
import pkg.misc as misc

import pkg.server.face as face
import pkg.server.config as config
import pkg.server.transaction as trans

def usage():
        print """\
Usage: /usr/lib/pkg.depotd [--readonly] [--rebuild] [-d repo_dir] [-p port]
        --readonly      Read-only operation; modifying operations disallowed
        --rebuild       Re-build the catalog from pkgs in depot
"""
        sys.exit(2)

def versions_0(scfg, request):
        request.send_response(200)
        request.send_header('Content-type', 'text/plain')
        request.end_headers()
        versions = "\n".join(
            "%s %s" % (op, " ".join(vers))
            for op, vers in vops.iteritems()
        ) + "\n"
        request.wfile.write(versions)

def search_0(scfg, request):
        try:
                token = urllib.unquote(request.path.split("/", 3)[3])
        except IndexError:
                request.send_response(400)
                return

        if not token:
                request.send_response(400)
                return

        if not scfg.search_available():
                request.send_response(503, "Search temporarily unavailable")
                return

        try:
                res = scfg.catalog.search(token)
        except KeyError:
                request.send_response(404)
                return

        request.send_response(200)
        request.send_header("Content-type", "text/plain")
        request.end_headers()
        for l in res:
                request.wfile.write("%s %s\n" % (l[0], l[1]))

def catalog_0(scfg, request):
        scfg.inc_catalog()

        # Try to guard against a non-existent catalog.  The catalog open will
        # raise an exception, and only the attributes will have been sent.  But
        # because we've sent data already (never mind the response header), we
        # can't raise an exception here, or a 500 header will get sent as well.
        try:
                scfg.updatelog.send(request)
        except:
                request.log_error("Internal failure:\n%s",
                    traceback.format_exc())

def manifest_0(scfg, request):
        """The request is an encoded pkg FMRI.  If the version is specified
        incompletely, we return an error, as the client is expected to form
        correct requests, based on its interpretation of the catalog and its
        image policies."""

        scfg.inc_manifest()

        # Parse request into FMRI component and decode.
        pfmri = urllib.unquote(request.path.split("/", 3)[-1])

        f = fmri.PkgFmri(pfmri, None)

        # Open manifest and send.
        try:
                file = open("%s/%s" % (scfg.pkg_root, f.get_dir_path()), "r")
        except IOError, e:
                if e.errno == errno.ENOENT:
                        request.send_response(404)
                else:
                        request.log_error("Internal failure:\n%s",
                            traceback.format_exc())
                        request.send_response(500)
                return
        data = file.read()

        request.send_response(200)
        request.send_header('Content-type', 'text/plain')
        request.end_headers()
        request.wfile.write(data)

def filelist_0(scfg, request):
        """Request data contains application/x-www-form-urlencoded entries
        with the requested filenames."""
        # If the sender doesn't specify the content length, reject this request.
        # Calling read() with no size specified will force the server to block
        # until the client sends EOF, an undesireable situation
        size = int(request.headers.getheader("Content-Length", "0"))
        if size == 0:
                request.send_response(411)
                return

        rfile = request.rfile
        data_dict = cgi.parse_qs(rfile.read(size))

        scfg.inc_flist()

        request.send_response(200)
        request.send_header("Content-type", "application/data")
        request.end_headers()

        tar_stream = tarfile.open(mode = "w|", fileobj = request.wfile)

        for v in data_dict.values():
                filepath = os.path.normpath(os.path.join(
                    scfg.file_root, misc.hash_file_name(v[0])))

                tar_stream.add(filepath, v[0], False)
                scfg.inc_flist_files()

        tar_stream.close()

def file_0(scfg, request):
        """The request is the SHA-1 hash name for the file."""
        scfg.inc_file()

        fhash = request.path.split("/", 3)[-1]

        try:
                file = open(os.path.normpath(os.path.join(
                    scfg.file_root, misc.hash_file_name(fhash))))
        except IOError, e:
                if e.errno == errno.ENOENT:
                        request.send_response(404)
                else:
                        request.log_error("Internal failure:\n%s",
                            traceback.format_exc())
                        request.send_response(500)
                return

        data = file.read()

        request.send_response(200)
        request.send_header("Content-type", "application/data")
        request.end_headers()
        request.wfile.write(data)

def open_0(scfg, request):
        # XXX Authentication will be handled by virtue of possessing a signed
        # certificate (or a more elaborate system).
        if scfg.is_read_only():
                request.send_error(403, "Read-only server")
                return

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


def close_0(scfg, request):
        if scfg.is_read_only():
                request.send_error(403, "Read-only server")
                return

        # Pull transaction ID from headers.
        trans_id = request.path.split("/", 3)[-1]

        try:
                t = scfg.in_flight_trans[trans_id]
        except KeyError:
                request.send_response(404, "Transaction ID not found")
        else:
                t.close(request)
                del scfg.in_flight_trans[trans_id]

def abandon_0(scfg, request):
        if scfg.is_read_only():
                request.send_error(403, "Read-only server")
                return

        # Pull transaction ID from headers.
        trans_id = request.path.split("/", 3)[-1]

        try:
                t = scfg.in_flight_trans[trans_id]
        except KeyError:
                request.send_response(404, "Transaction ID not found")
        else:
                t.abandon(request)
                del scfg.in_flight_trans[trans_id]

def add_0(scfg, request):
        if scfg.is_read_only():
                request.send_error(403, "Read-only server")
                return

        trans_id, type = request.path.split("/", 4)[-2:]

        try:
                t = scfg.in_flight_trans[trans_id]
        except KeyError:
                request.send_response(404, "Transaction ID not found")
        else:
                t.add_content(request, type)

if "PKG_REPO" in os.environ:
        scfg = config.SvrConfig(os.environ["PKG_REPO"], "pkg.sun.com")
else:
        scfg = config.SvrConfig("/var/pkg/repo", "pkg.sun.com")

def set_ops():
        vops = {}
        for name in globals():
                m = re.match("(.*)_(\d+)", name)

                if not m:
                        continue

                op = m.group(1)
                ver = m.group(2)

                if op in vops:
                        vops[op].append(ver)
                else:
                        vops[op] = [ ver ]

        return vops

class pkgHandler(BaseHTTPServer.BaseHTTPRequestHandler):

        def address_string(self):
                host, port = self.client_address[:2]
                return host

        def do_GET(self):
                reqarr = self.path.lstrip("/").split("/")
                operation = reqarr[0]

                if operation not in vops:
                        if face.match(self):
                                face.respond(scfg, self)
                        else:
                                face.unknown(scfg, self)
                        return

                # Make sure that we have a integer protocol version
                try:
                        version = int(reqarr[1])
                except IndexError, e:
                        self.send_response(400)
                        self.send_header("Content-type", "text/plain")
                        self.end_headers()
                        self.wfile.write("Missing version\n")
                        return
                except ValueError, e:
                        self.send_response(400)
                        self.send_header("Content-type", "text/plain")
                        self.end_headers()
                        self.wfile.write("Non-integer version\n")
                        return

                op_method = "%s_%s" % (operation, version)
                if op_method not in globals():
                        # If we get here, we know that 'operation' is supported.
                        # Assume 'version' is not supported for that operation.
                        self.send_response(404, "Version not supported")
                        self.send_header("Content-type", "text/plain")
                        self.end_headers()

                        vns = "Version '%s' not supported for operation '%s'\n"
                        self.wfile.write(vns % (version, operation))
                        return

                op_call = op_method + "(scfg, self)"

                try:
                        exec op_call
                except:
                        self.log_error("Internal failure:\n%s",
                            traceback.format_exc())
                        # XXX op_call may already have spit some data out to the
                        # client, in which case this response just corrupts that
                        # datastream.  I don't know of any way to tell whether
                        # data has already been sent.
                        self.send_response(500)

        def do_POST(self):
                self.do_GET()

        def do_PUT(self):
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write('''PUT URI %s ; headers %s''' %
                    (self.path, self.headers))

        def do_DELETE(self):
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write('''URI %s ; headers %s''' %
                    (self.path, self.headers))

class ThreadingHTTPServer(SocketServer.ThreadingMixIn,
    BaseHTTPServer.HTTPServer):
        pass

vops = {}

if __name__ == "__main__":
        port = 80
        unprivport = 10000

        if "PKG_DEPOT_CONTENT" in os.environ:
                face.set_content_root(os.environ["PKG_DEPOT_CONTENT"])

        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "d:np:",
                    ["readonly", "rebuild"])
                for opt, arg in opts:
                        if opt == "-n":
                                sys.exit(0)
                        elif opt == "-d":
                                scfg.set_repo_root(arg)
                        elif opt == "-p":
                                port = int(arg)
                        elif opt == "--readonly":
                                scfg.set_read_only()
                        elif opt == "--rebuild":
                                scfg.destroy_catalog()
        except getopt.GetoptError, e:
                print "pkg.depotd: illegal option -- %s" % e.opt
                usage()

        scfg.init_dirs()
        scfg.acquire_in_flight()
        scfg.acquire_catalog()

        vops = set_ops()

        try:
                server = ThreadingHTTPServer(('', port), pkgHandler)
        except socket.error, e:
                if e.args[0] != errno.EACCES:
                        raise

                server = ThreadingHTTPServer(('', unprivport), pkgHandler)
                print >> sys.stderr, \
                     "Insufficient privilege to bind to port %d." % port
                print >> sys.stderr, \
                    "Bound server to port %d instead." % unprivport
                print >> sys.stderr, \
                    "Use the -p option to pick another port, if desired."

        server.serve_forever()
