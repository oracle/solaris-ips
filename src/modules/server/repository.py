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
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import cherrypy
from cherrypy.lib.static import serve_file

import errno
import httplib
import inspect
import logging
import os
import re
import socket

import tarfile
# Without the below statements, tarfile will trigger calls to getpwuid and
# getgrgid for every file downloaded.  This in turn leads to nscd usage which
# limits the throughput of the depot process.  Setting these attributes to
# undefined causes tarfile to skip these calls in tarfile.gettarinfo().  This
# information is unnecesary as it will not be used by the client.
tarfile.pwd = None
tarfile.grp = None

import urllib

import pkg.server.catalog as catalog
import pkg.fmri as fmri
import pkg.misc as misc
import pkg.Uuid25 as uuid

import pkg.server.repositoryconfig as rc
import pkg.server.face as face
import pkg.server.transaction as trans

class Dummy(object):
        """ Dummy object used for dispatch method mapping. """
        pass

class Repository(object):
        """ Repository configuration and state object used as an abstraction
            abstraction layer above our web framework and the underlying objects
            that perform various operations.  This also should make it easy (in
            theory) to instantiate and manage multiple repositories for a single
            depot process. """

        def __init__(self, scfg):
                """ Initialise and map the valid operations for the repository.
                    While doing so, ensure that the operations have been
                    explicitly "exposed" for external usage. """

                self.scfg = scfg

                # Now load our repository configuration / metadata and
                # populate our repository.id if needed.
                cfgpathname = os.path.join(scfg.repo_root, "cfg_cache")

                # Check to see if our configuration file exists first.
                if os.path.exists(cfgpathname):
                        self.rcfg = rc.RepositoryConfig(pathname=cfgpathname)
                else:
                        # If it doesn't exist, just create a new object, it
                        # will automatically be populated with sane defaults.
                        self.rcfg = rc.RepositoryConfig()

                if not self.scfg.is_read_only():
                        # While our configuration can be parsed during
                        # initialization, no changes can be written to disk
                        # in readonly mode.

                        # RSS/Atom feeds require a unique identifier, so
                        # generate one if isn't defined already.  This
                        # needs to be a persistent value, so we only
                        # generate this if we can save the configuration.
                        fid = self.rcfg.get_attribute("feed", "id")
                        if not fid:
                                # Create a random UUID (type 4).
                                self.rcfg._set_attribute("feed", "id",
                                    uuid.uuid4())

                        # Save the new configuration (or refresh existing).
                        self.rcfg.write(cfgpathname)

                self.vops = {}

                # cherrypy has a special handler for favicon, and so we must
                # setup an instance-level handler instead of just updating
                # its configuration information.
                self.favicon_ico = cherrypy.tools.staticfile.handler(
                    os.path.join(face.content_root,
                    self.rcfg.get_attribute("repository", "icon")))

                for name, func in inspect.getmembers(self, inspect.ismethod):
                        m = re.match("(.*)_(\d+)", name)

                        if not m:
                                continue

                        # We only want to allow operations we have explicitly
                        # exposed.  cherrypy will handle this automatically,
                        # but this prevents a bad operator from being put
                        # into vops.
                        assert getattr(func, 'exposed', False), "Unable to " \
                            "map operation %s; not explicitly exposed." % name

                        op = m.group(1)
                        ver = m.group(2)

                        if op in self.vops:
                                self.vops[op].append(ver)
                        else:
                                # We need a Dummy object here since we need to
                                # be able to set arbitrary attributes that
                                # contain function pointers to our object
                                # instance.  CherryPy relies on this for its
                                # dispatch tree mapping mechanism.  We can't
                                # use other object types here since Python
                                # won't let us set arbitary attributes on them.
                                setattr(self, op, Dummy())
                                self.vops[op] = [ver]

                        opattr = getattr(self, op)
                        setattr(opattr, ver, func)

        @cherrypy.expose
        def default(self, *tokens, **params):
                """ Any request that is not explicitly mapped to the repository
                    object will be handled by the "externally facing" server
                    code instead. """

                operation = None
                if len(tokens) > 0:
                        operation = tokens[0]

                if operation not in self.vops:
                        request = cherrypy.request
                        response = cherrypy.response
                        if face.match(self.scfg, self.rcfg, request, response):
                                return face.respond(self.scfg, self.rcfg,
                                    request, response)
                        else:
                                return face.unknown(self.scfg, self.rcfg,
                                    request, response)

                # If we get here, we know that 'operation' is supported.
                # Ensure that we have a integer protocol version.
                try:
                        version = int(tokens[1])
                except IndexError:
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST,
                            "Missing version\n")
                except ValueError:
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST,
                            "Non-integer version\n")

                # Assume 'version' is not supported for the operation.
                msg = "Version '%s' not supported for operation '%s'\n" \
                    % (version, operation)
                raise cherrypy.HTTPError(httplib.NOT_FOUND, msg)

        @cherrypy.expose
        @cherrypy.tools.response_headers(headers = \
            [('Content-Type','text/plain')])
        def versions_0(self, *tokens):
                """ Output a text/plain list of valid operations, and their
                    versions, supported by the repository. """

                versions = "\n".join(
                    "%s %s" % (op, " ".join(vers))
                    for op, vers in self.vops.iteritems()
                ) + "\n"
                return versions

        @cherrypy.expose
        def search_0(self, *tokens):
                """ Based on the request path, return a list of packages that
                    match the specified criteria. """

                response = cherrypy.response

                try:
                        token = tokens[0]
                except IndexError:
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST)

                if not token:
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST)

                if not self.scfg.search_available():
                        raise cherrypy.HTTPError(httplib.SERVICE_UNAVAILABLE,
                            "Search temporarily unavailable")

                res = self.scfg.catalog.search(token)

                response.headers['Content-type'] = 'text/plain'

                output = ""
                # The query_engine returns four pieces of information in the
                # proper order. Put those four pieces of information into a
                # string that the client can understand.
                for l in res:
                        output += ("%s %s %s %s\n" % (l[0], l[1], l[2], l[3]))

                return output

        @cherrypy.expose
        def catalog_0(self, *tokens):
                """ Provide an incremental update or full version of the
                    catalog as appropriate to the requesting client. """

                self.scfg.inc_catalog()

                # Try to guard against a non-existent catalog.  The catalog
                # open will raise an exception, and only the attributes will
                # have been sent.  But because we've sent data already (never
                # mind the response header), we can't raise an exception here,
                # or an INTERNAL_SERVER_ERROR header will get sent as well.
                try:
                        return self.scfg.updatelog.send(cherrypy.request,
                            cherrypy.response)
                except socket.error, e:
                        if e.args[0] == errno.EPIPE:
                                return

                        cherrypy.log("Internal failure:\n",
                            severity = logging.CRITICAL, traceback = True)

        catalog_0._cp_config = { 'response.stream': True }

        @cherrypy.expose
        def manifest_0(self, *tokens):
                """ The request is an encoded pkg FMRI.  If the version is
                    specified incompletely, we return an error, as the client
                    is expected to form correct requests, based on its
                    interpretation of the catalog and its image policies. """

                self.scfg.inc_manifest()

                # Parse request into FMRI component and decode.
                try:
                        pfmri = tokens[0]
                except IndexError:
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST)

                f = fmri.PkgFmri(pfmri, None)

                # send manifest
                return serve_file("%s/%s" % (self.scfg.pkg_root,
                    f.get_dir_path()), 'text/plain')

        @staticmethod
        def _tar_stream_close(**kwargs):
                """ This is a special function to finish a tar_stream-based
                    request; to be called by cherrypy. """

                tar_stream = cherrypy.request.tar_stream
                if tar_stream:
                        try:
                                # Attempt to close the tar_stream now that we
                                # are done processing the request.
                                tar_stream.close()
                        except Exception, e:
                                # tarfile most likely failed trying to flush
                                # its internal buffer.  To prevent tarfile from
                                # causing further exceptions during __del__,
                                # we have to lie and say the fileobj has been
                                # closed.
                                tar_stream.fileobj.closed = True
                                cherrypy.log("Request aborted.")

                        cherrypy.request.tar_stream = None

        @cherrypy.expose
        def filelist_0(self, *tokens, **params):
                """ Request data contains application/x-www-form-urlencoded
                    entries with the requested filenames.  The resulting tar
                    stream is output directly to the client. """

                try:
                        self.scfg.inc_flist()

                        # We pass the response object directly to tarfile
                        # since it has a write() callable which is all tarfile
                        # needs to output the stream.  This will write the
                        # bytes to the client through our parent server
                        # process.
                        tar_stream = tarfile.open(mode = "w|",
                            fileobj = cherrypy.response)

                        # We can use the request object for storage of data
                        # specific to this request.  In this case, it allows us
                        # to provide our on_end_request function with access
                        # to the stream we are processing.
                        cherrypy.request.tar_stream = tar_stream

                        # This is a special hook just for this request so that
                        # even if an exception is encountered, the stream will
                        # be closed properly regardless of which thread is
                        # executing.
                        cherrypy.request.hooks.attach('on_end_request',
                            self._tar_stream_close, failsafe = True)

                        for v in params.values():
                                filepath = os.path.normpath(os.path.join(
                                    self.scfg.file_root,
                                    misc.hash_file_name(v)))

                                tar_stream.add(filepath, v, False)

                                self.scfg.inc_flist_files()
                except Exception, e:
                        # If we find an exception of this type, the
                        # client has most likely been interrupted.
                        if isinstance(e, socket.error) \
                            and e.args[0] == errno.EPIPE:
                                return

                yield ""

        # We have to configure the headers either through the _cp_config
        # namespace, or inside the function itself whenever we are using
        # a streaming generator.  This is because headers have to be setup
        # before the response even begins and the point at which @tools
        # hooks in is too late.
        filelist_0._cp_config = {
                'response.stream': True,
                'tools.response_headers.on': True,
                'tools.response_headers.headers': [('Content-Type',
                    'application/data')]
        }

        @cherrypy.expose
        def rename_0(self, *tokens, **params):
                """ Renames an existing package specified by Src-FMRI to
                    Dest-FMRI.  Returns no output. """

                try:
                        src_fmri = fmri.PkgFmri(params['Src-FMRI'], None)
                except KeyError:
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST,
                            "No source FMRI present.")
                except ValueError:
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST,
                            "Invalid source FMRI.")
                except AssertionError:
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST,
                            "Source FMRI must contain build string.")

                try:
                        dest_fmri = fmri.PkgFmri(params['Dest-FMRI'], None)
                except KeyError:
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST,
                            "No destination FMRI present.")
                except ValueError:
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST,
                            "Invalid destination FMRI.")
                except AssertionError:
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST,
                            "Destination FMRI must contain build string.")

                try:
                        self.scfg.updatelog.rename_package(src_fmri.pkg_name,
                            str(src_fmri.version), dest_fmri.pkg_name,
                            str(dest_fmri.version))
                except catalog.CatalogException, e:
                        raise cherrypy.HTTPError(httplib.NOT_FOUND, e.args)
                except catalog.RenameException, e:
                        raise cherrypy.HTTPError(httplib.NOT_FOUND, e.args)

                self.scfg.inc_renamed()

        @cherrypy.expose
        def file_0(self, *tokens):
                """ The request is the SHA-1 hash name for the file.  The
                    contents of the file is output directly to the client. """
                self.scfg.inc_file()

                try:
                        fhash = tokens[0]
                except IndexError:
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST)

                return serve_file(os.path.normpath(os.path.join(
                    self.scfg.file_root, misc.hash_file_name(fhash))),
                    'application/data')

        @cherrypy.expose
        def open_0(self, *tokens):
                """ Starts a transaction for the package name specified in the
                    request path.  Returns no output."""

                response = cherrypy.response

                # XXX Authentication will be handled by virtue of possessing a
                # signed certificate (or a more elaborate system).
                if self.scfg.is_read_only():
                        raise cherrypy.HTTPError(httplib.FORBIDDEN,
                            "Read-only server")

                t = trans.Transaction()
                ret = t.open(self.scfg, *tokens)
                if ret == httplib.OK:
                        self.scfg.in_flight_trans[t.get_basename()] = t
                        response.headers['Content-type'] = 'text/plain'
                        response.headers['Transaction-ID'] = t.get_basename()
                elif ret == httplib.BAD_REQUEST:
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST)
                else:
                        raise cherrypy.HTTPError(httplib.INTERNAL_SERVER_ERROR)

        @cherrypy.expose
        def close_0(self, *tokens):
                """ Ends an in-flight transaction for the Transaction ID
                    specified in the request path.  Returns no output. """

                if self.scfg.is_read_only():
                        raise cherrypy.HTTPError(httplib.FORBIDDEN,
                            "Read-only server")

                try:
                        # cherrypy decoded it, but we actually need it encoded.
                        trans_id = urllib.quote("%s" % tokens[0], "")
                except IndexError:
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST)

                try:
                        t = self.scfg.in_flight_trans[trans_id]
                except KeyError:
                        raise cherrypy.HTTPError(httplib.NOT_FOUND,
                            "close Transaction ID not found")
                else:
                        t.close()
                        del self.scfg.in_flight_trans[trans_id]

        @cherrypy.expose
        def abandon_0(self, *tokens):
                """ Aborts an in-flight transaction for the Transaction ID
                    specified in the request path.  Returns no output. """

                if self.scfg.is_read_only():
                        raise cherrypy.HTTPError(httplib.FORBIDDEN,
                            "Read-only server")
                try:
                        # cherrypy decoded it, but we actually need it encoded.
                        trans_id = urllib.quote("%s" % tokens[0], "")
                except IndexError:
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST)

                try:
                        t = self.scfg.in_flight_trans[trans_id]
                except KeyError:
                        raise cherrypy.HTTPError(httplib.NOT_FOUND,
                            "Transaction ID not found")
                else:
                        t.abandon()
                        del self.scfg.in_flight_trans[trans_id]

        @cherrypy.expose
        def add_0(self, *tokens, **params):
                """ Adds content to an in-flight transaction for the
                    Transaction ID specified in the request path.  The content
                    is expected to be in the request body.  Returns no
                    output. """

                if self.scfg.is_read_only():
                        raise cherrypy.HTTPError(httplib.FORBIDDEN,
                            "Read-only server")

                try:
                        # cherrypy decoded it, but we actually need it encoded.
                        trans_id = urllib.quote("%s" % tokens[0], "")
                        entry_type = tokens[1]
                except IndexError:
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST)

                try:
                        t = self.scfg.in_flight_trans[trans_id]
                except KeyError:
                        raise cherrypy.HTTPError(httplib.NOT_FOUND,
                            "Transaction ID not found")
                else:
                        t.add_content(entry_type)

        # We need to prevent cherrypy from processing the request body so that
        # add can parse the request body itself.  In addition, we also need to
        # set the timeout higher since the default is five minutes; not really
        # enough for a slow connection to upload content.
        add_0._cp_config = {
                'request.process_request_body': False,
                'response.timeout': 3600,
        }

