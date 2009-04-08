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
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import cherrypy
from cherrypy.lib.static import serve_file

import cStringIO
import errno
import httplib
import inspect
import itertools
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

import pkg
import pkg.actions as actions
import pkg.catalog as catalog
import pkg.fmri as fmri
import pkg.manifest as manifest
import pkg.misc as misc

import pkg.server.face as face
import pkg.server.repository as repo

from pkg.server.query_parser import Query

class Dummy(object):
        """Dummy object used for dispatch method mapping."""
        pass

class DepotHTTP(object):
        """The DepotHTTP object is intended to be used as a cherrypy
        application object and represents the set of operations that a
        pkg.depotd server provides to HTTP-based clients."""

        REPO_OPS_DEFAULT = [
            "versions",
            "search",
            "catalog",
            "info",
            "manifest",
            "filelist",
            "rename",
            "file",
            "open",
            "close",
            "abandon",
            "add"
        ]

        REPO_OPS_READONLY = [
            "versions",
            "search",
            "catalog",
            "info",
            "manifest",
            "filelist",
            "file"
        ]

        REPO_OPS_MIRROR = [
            "versions",
            "filelist",
            "file"
        ]

        def __init__(self, scfg, cfgpathname=None):
                """Initialize and map the valid operations for the depot.  While
                doing so, ensure that the operations have been explicitly
                "exposed" for external usage."""

                self.__repo = repo.Repository(scfg, cfgpathname)
                self.rcfg = self.__repo.rcfg
                self.scfg = self.__repo.scfg

                # Handles the BUI (Browser User Interface).
                face.init(scfg, self.rcfg)

                # Store any possible configuration changes.
                self.__repo.write_config()

                if scfg.is_mirror():
                        self.ops_list = self.REPO_OPS_MIRROR
                elif scfg.is_read_only():
                        self.ops_list = self.REPO_OPS_READONLY
                else:
                        self.ops_list = self.REPO_OPS_DEFAULT

                self.vops = {}
                for name, func in inspect.getmembers(self, inspect.ismethod):
                        m = re.match("(.*)_(\d+)", name)

                        if not m:
                                continue

                        op = m.group(1)
                        ver = m.group(2)

                        if op not in self.ops_list:
                                continue

                        func.__dict__["exposed"] = True

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
                """Any request that is not explicitly mapped to the repository
                object will be handled by the "externally facing" server
                code instead."""

                op = None
                if len(tokens) > 0:
                        op = tokens[0]

                if op in self.REPO_OPS_DEFAULT and op not in self.vops:
                        raise cherrypy.HTTPError(httplib.NOT_FOUND,
                            "Operation not supported in current server mode.")
                elif op not in self.vops:
                        request = cherrypy.request
                        response = cherrypy.response
                        return face.respond(self.scfg, self.rcfg,
                            request, response, *tokens, **params)

                # If we get here, we know that 'operation' is supported.
                # Ensure that we have a integer protocol version.
                try:
                        ver = int(tokens[1])
                except IndexError:
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST,
                            "Missing version\n")
                except ValueError:
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST,
                            "Non-integer version\n")

                # Assume 'version' is not supported for the operation.
                raise cherrypy.HTTPError(httplib.NOT_FOUND, "Version '%s' not "
                    "supported for operation '%s'\n" % (ver, op))

        @cherrypy.tools.response_headers(headers = \
            [("Content-Type", "text/plain")])
        def versions_0(self, *tokens):
                """Output a text/plain list of valid operations, and their
                versions, supported by the repository."""

                versions = "pkg-server %s\n" % pkg.VERSION
                versions += "\n".join(
                    "%s %s" % (op, " ".join(vers))
                    for op, vers in self.vops.iteritems()
                ) + "\n"
                return versions

        def search_0(self, *tokens):
                """Based on the request path, return a list of token type / FMRI
                pairs."""

                response = cherrypy.response
                response.headers["Content-type"] = "text/plain"

                try:
                        token = tokens[0]
                except IndexError:
                        token = None

                query_args_lst = [str(Query(token, case_sensitive=False,
                    return_type=Query.RETURN_ACTIONS, num_to_return=None,
                    start_point=None))]
                        
                try:
                        res_list = self.__repo.search(query_args_lst)
                except repo.RepositorySearchUnavailableError, e:
                        raise cherrypy.HTTPError(httplib.SERVICE_UNAVAILABLE,
                            str(e))
                except repo.RepositoryError, e:
                        # Treat any remaining repository error as a 404, but
                        # log the error and include the real failure
                        # information.
                        cherrypy.log("Request failed: %s" % str(e))
                        raise cherrypy.HTTPError(httplib.NOT_FOUND, str(e))

                def output():
                        for i, res in enumerate(res_list):
                                for v, return_type, vals in res:
                                        fmri_str, fv, line = vals
                                        a = actions.fromstr(line.rstrip())
                                        if isinstance(a,
                                            actions.attribute.AttributeAction):
                                                yield "%s %s %s %s\n" % \
                                                    (a.attrs.get(a.key_attr),
                                                    fmri_str, a.name, fv)
                                        else:
                                                yield "%s %s %s %s\n" % \
                                                    (fv, fmri_str, a.name,
                                                    a.attrs.get(a.key_attr))

                return output()

        search_0._cp_config = { "response.stream": True }

        
        def search_1(self, *args, **params):
                """Based on the request path, return a list of packages that
                match the specified criteria."""
                query_str_lst = []

                try:
                        query_str_lst = [args[0]]
                except IndexError:
                        pass

                if not query_str_lst:
                        query_str_lst = params.values()
                elif params.values():
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST,
                            "args:%s, params:%s" % (args, params))

                if not query_str_lst:
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST)

                response = cherrypy.response

                if not self.scfg.search_available():
                        raise cherrypy.HTTPError(httplib.SERVICE_UNAVAILABLE,
                            "Search temporarily unavailable")

                try:
                        res_list = self.__repo.search(query_str_lst)
                except repo.RepositorySearchUnavailableError, e:
                        raise cherrypy.HTTPError(httplib.SERVICE_UNAVAILABLE,
                            str(e))
                except repo.RepositoryError, e:
                        # Treat any remaining repository error as a 404, but
                        # log the error and include the real failure
                        # information.
                        cherrypy.log("Request failed: %s" % str(e))
                        raise cherrypy.HTTPError(httplib.NOT_FOUND, str(e))

                response.headers["Content-type"] = "text/plain"

                if len(res_list) == 1:
                        try:
                                tmp = res_list[0].next()
                                res_list = [itertools.chain([tmp], res_list[0])]
                        except StopIteration:
                                cherrypy.response.status = httplib.NO_CONTENT
                                return
                
                def output():
                        yield str(Query.VALIDATION_STRING[1])
                        for i, res in enumerate(res_list):
                                for v, return_type, vals in res:
                                        if return_type == Query.RETURN_ACTIONS:
                                                fmri_str, fv, line = vals
                                                yield "%s %s %s %s %s\n" % \
                                                    (i, return_type, fmri_str,
                                                    urllib.quote(fv),
                                                    line.rstrip())
                                        elif return_type == \
                                            Query.RETURN_PACKAGES:
                                                fmri_str = vals
                                                yield "%s %s %s\n" % \
                                                    (i, return_type, fmri_str)
                return output()

        search_1._cp_config = { "response.stream": True }


        def catalog_0(self, *tokens):
                """Provide an incremental update or full version of the
                catalog, as appropriate, to the requesting client."""

                request = cherrypy.request

                response = cherrypy.response
                response.headers["Content-type"] = "text/plain"
                response.headers["Last-Modified"] = \
                    self.scfg.catalog.last_modified()

                lm = request.headers.get("If-Modified-Since", None)
                if lm is not None:
                        try:
                                lm = catalog.ts_to_datetime(lm)
                        except ValueError:
                                lm = None
                        else:
                                if not self.scfg.updatelog.enough_history(lm):
                                        # Ignore incremental requests if there
                                        # isn't enough history to provide one.
                                        lm = None
                                elif self.scfg.updatelog.up_to_date(lm):
                                        response.status = httplib.NOT_MODIFIED
                                        return

                if lm:
                        # If a last modified date and time was provided, then an
                        # incremental update is being requested.
                        response.headers["X-Catalog-Type"] = "incremental"
                else:
                        response.headers["X-Catalog-Type"] = "full"
                        response.headers["Content-Length"] = str(
                            self.scfg.catalog.size())

                def output():
                        try:
                                for l in self.__repo.catalog(lm):
                                        yield l
                        except repo.RepositoryError, e:
                                # Can't do anything in a streaming generator
                                # except log the error and return.
                                cherrypy.log("Request failed: %s" % str(e))
                                return

                return output()

        catalog_0._cp_config = { "response.stream": True }

        def manifest_0(self, *tokens):
                """The request is an encoded pkg FMRI.  If the version is
                specified incompletely, we return an error, as the client is
                expected to form correct requests based on its interpretation
                of the catalog and its image policies."""

                # Parse request into FMRI component and decode.
                try:
                        # If more than one token (request path component) was
                        # specified, assume that the extra components are part
                        # of the fmri and have been split out because of bad
                        # proxy behaviour.
                        pfmri = "/".join(tokens)
                        fpath = self.__repo.manifest(pfmri)
                except (IndexError, repo.RepositoryInvalidFMRIError), e:
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST, str(e))
                except repo.RepositoryError, e:
                        # Treat any remaining repository error as a 404, but
                        # log the error and include the real failure
                        # information.
                        cherrypy.log("Request failed: %s" % str(e))
                        raise cherrypy.HTTPError(httplib.NOT_FOUND, str(e))

                # Send manifest
                return serve_file(fpath, "text/plain")

        manifest_0._cp_config = { "response.stream": True }

        @staticmethod
        def _tar_stream_close(**kwargs):
                """This is a special function to finish a tar_stream-based
                request in the event of an exception."""

                tar_stream = cherrypy.request.tar_stream
                if tar_stream:
                        try:
                                # Attempt to close the tar_stream now that we
                                # are done processing the request.
                                tar_stream.close()
                        except Exception:
                                # All exceptions are intentionally caught as
                                # this is a failsafe function and must happen.

                                # tarfile most likely failed trying to flush
                                # its internal buffer.  To prevent tarfile from
                                # causing further exceptions during __del__,
                                # we have to lie and say the fileobj has been
                                # closed.
                                tar_stream.fileobj.closed = True
                                cherrypy.log("Request aborted: ",
                                    traceback=True)

                        cherrypy.request.tar_stream = None

        def filelist_0(self, *tokens, **params):
                """Request data contains application/x-www-form-urlencoded
                entries with the requested filenames.  The resulting tar stream
                is output directly to the client. """

                try:
                        self.scfg.inc_flist()

                        # Create a dummy file object that hooks to the write()
                        # callable which is all tarfile needs to output the
                        # stream.  This will write the bytes to the client
                        # through our parent server process.
                        f = Dummy()
                        f.write = cherrypy.response.write

                        tar_stream = tarfile.open(mode = "w|",
                            fileobj = f)

                        # We can use the request object for storage of data
                        # specific to this request.  In this case, it allows us
                        # to provide our on_end_request function with access to
                        # the stream we are processing.
                        cherrypy.request.tar_stream = tar_stream

                        # This is a special hook just for this request so that
                        # if an exception is encountered, the stream will be
                        # closed properly regardless of which thread is
                        # executing.
                        cherrypy.request.hooks.attach("on_end_request",
                            self._tar_stream_close, failsafe = True)

                        for v in params.values():
                                filepath = os.path.normpath(os.path.join(
                                    self.scfg.file_root,
                                    misc.hash_file_name(v)))

                                # If file isn't here, skip it
                                if not os.path.exists(filepath):
                                        continue

                                tar_stream.add(filepath, v, False)

                                self.scfg.inc_flist_files()

                        # Flush the remaining bytes to the client.
                        tar_stream.close()
                        cherrypy.request.tar_stream = None

                except Exception, e:
                        # If we find an exception of this type, the
                        # client has most likely been interrupted.
                        if isinstance(e, socket.error) \
                            and e.args[0] == errno.EPIPE:
                                return
                        raise

                yield ""

        # We have to configure the headers either through the _cp_config
        # namespace, or inside the function itself whenever we are using
        # a streaming generator.  This is because headers have to be setup
        # before the response even begins and the point at which @tools
        # hooks in is too late.
        filelist_0._cp_config = {
                "response.stream": True,
                "tools.response_headers.on": True,
                "tools.response_headers.headers": [("Content-Type",
                "application/data")]
        }

        def rename_0(self, *tokens, **params):
                """Renames an existing package specified by Src-FMRI to
                Dest-FMRI.  Returns no output."""

                try:
                        src_fmri = params["Src-FMRI"]
                except KeyError:
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST,
                            "No source FMRI present.")

                try:
                        dest_fmri = params['Dest-FMRI']
                except KeyError:
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST,
                            "No destination FMRI present.")

                try:
                        self.__repo.rename(src_fmri, dest_fmri)
                except (repo.RepositoryInvalidFMRIError,
                    repo.RepositoryRenameFailureError), e:
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST, str(e))
                except repo.RepositoryError, e:
                        # Treat any remaining repository error as a 404, but
                        # log the error and include the real failure
                        # information.
                        cherrypy.log("Request failed: %s" % str(e))
                        raise cherrypy.HTTPError(httplib.NOT_FOUND, str(e))

        def file_0(self, *tokens):
                """Outputs the contents of the file, named by the SHA-1 hash
                name in the request path, directly to the client."""

                try:
                        fhash = tokens[0]
                except IndexError:
                        fhash = None

                try:
                        fpath = self.__repo.file(fhash)
                except repo.RepositoryFileNotFoundError, e:
                        raise cherrypy.HTTPError(httplib.NOT_FOUND, str(e))
                except repo.RepositoryError, e:
                        # Treat any remaining repository error as a 404, but
                        # log the error and include the real failure
                        # information.
                        cherrypy.log("Request failed: %s" % str(e))
                        raise cherrypy.HTTPError(httplib.NOT_FOUND, str(e))

                return serve_file(fpath, "application/data")

        file_0._cp_config = { "response.stream": True }

        def open_0(self, *tokens):
                """Starts a transaction for the package name specified in the
                request path.  Returns no output."""

                request = cherrypy.request
                response = cherrypy.response

                client_release = request.headers.get("Client-Release", None)
                try:
                        pfmri = tokens[0]
                except IndexError:
                        pfmri = None

                # XXX Authentication will be handled by virtue of possessing a
                # signed certificate (or a more elaborate system).

                try:
                        trans_id = self.__repo.open(client_release, pfmri)
                        response.headers["Content-type"] = "text/plain"
                        response.headers["Transaction-ID"] = trans_id
                except repo.RepositoryError, e:
                        # Treat any remaining repository error as a 404, but
                        # log the error and include the real failure
                        # information.
                        cherrypy.log("Request failed: %s" % str(e))
                        raise cherrypy.HTTPError(httplib.NOT_FOUND, str(e))

        def close_0(self, *tokens):
                """Ends an in-flight transaction for the Transaction ID
                specified in the request path.

                Returns a Package-FMRI and State header in the response
                indicating the published FMRI and the state of the package
                in the catalog.  Returns no output."""

                try:
                        # cherrypy decoded it, but we actually need it encoded.
                        trans_id = urllib.quote(tokens[0], "")
                except IndexError:
                        trans_id = None

                request = cherrypy.request

                try:
                        # Assume "True" for backwards compatibility.
                        refresh_index = int(request.headers.get(
                            "X-IPkg-Refresh-Index", 1))

                        # Force a boolean value.
                        if refresh_index:
                                refresh_index = True
                        else:
                                refresh_index = False
                except ValueError, e:
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST,
                            "X-IPkg-Refresh-Index: %s" % e)

                try:
                        pfmri, pstate = self.__repo.close(trans_id,
                            refresh_index=refresh_index)
                except repo.RepositoryInvalidTransactionIDError, e:
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST, str(e))
                except repo.RepositoryError, e:
                        # Treat any remaining repository error as a 404, but
                        # log the error and include the real failure
                        # information.
                        cherrypy.log("Request failed: %s" % str(e))
                        raise cherrypy.HTTPError(httplib.NOT_FOUND, str(e))

                response = cherrypy.response
                response.headers["Package-FMRI"] = pfmri
                response.headers["State"] = pstate

        def abandon_0(self, *tokens):
                """Aborts an in-flight transaction for the Transaction ID
                specified in the request path.  Returns no output."""

                try:
                        # cherrypy decoded it, but we actually need it encoded.
                        trans_id = urllib.quote(tokens[0], "")
                except IndexError:
                        trans_id = None

                try:
                        self.__repo.abandon(trans_id)
                except repo.RepositoryInvalidTransactionIDError, e:
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST, str(e))
                except repo.RepositoryError, e:
                        # Treat any remaining repository error as a 404, but
                        # log the error and include the real failure
                        # information.
                        cherrypy.log("Request failed: %s" % str(e))
                        raise cherrypy.HTTPError(httplib.NOT_FOUND, str(e))

        def add_0(self, *tokens):
                """Adds an action and its content to an in-flight transaction
                for the Transaction ID specified in the request path.  The
                content is expected to be in the request body.  Returns no
                output."""

                try:
                        # cherrypy decoded it, but we actually need it encoded.
                        trans_id = urllib.quote(tokens[0], "")
                except IndexError:
                        trans_id = None

                try:
                        entry_type = tokens[1]
                except IndexError:
                        entry_type = None

                if entry_type not in actions.types:
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST, _("The "
                            "specified Action Type, '%s', is not valid.") % \
                            entry_type)

                request = cherrypy.request
                attrs = dict(
                    val.split("=", 1)
                    for hdr, val in request.headers.items()
                    if hdr.lower().startswith("x-ipkg-setattr")
                )

                # If any attributes appear to be lists, make them lists.
                for a in attrs:
                        if attrs[a].startswith("[") and attrs[a].endswith("]"):
                                # XXX there must be a better way than eval
                                attrs[a] = eval(attrs[a])

                data = None
                size = int(request.headers.get("Content-Length", 0))
                if size > 0:
                        data = request.rfile
                        # Record the size of the payload, if there is one.
                        attrs["pkg.size"] = str(size)

                action = actions.types[entry_type](data, **attrs)

                # XXX Once actions are labelled with critical nature.
                # if entry_type in critical_actions:
                #         self.critical = True

                try:
                        self.__repo.add(trans_id, action)
                except repo.RepositoryInvalidTransactionIDError, e:
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST, str(e))
                except repo.RepositoryError, e:
                        # Treat any remaining repository error as a 404, but
                        # log the error and include the real failure
                        # information.
                        cherrypy.log("Request failed: %s" % str(e))
                        raise cherrypy.HTTPError(httplib.NOT_FOUND, str(e))

        # We need to prevent cherrypy from processing the request body so that
        # add can parse the request body itself.  In addition, we also need to
        # set the timeout higher since the default is five minutes; not really
        # enough for a slow connection to upload content.
        add_0._cp_config = {
                "request.process_request_body": False,
                "response.timeout": 3600,
        }

        @cherrypy.tools.response_headers(headers = \
            [("Content-Type", "text/plain")])
        def info_0(self, *tokens):
                """ Output a text/plain summary of information about the
                    specified package. The request is an encoded pkg FMRI.  If
                    the version is specified incompletely, we return an error,
                    as the client is expected to form correct requests, based
                    on its interpretation of the catalog and its image
                    policies. """

                # Parse request into FMRI component and decode.
                try:
                        # If more than one token (request path component) was
                        # specified, assume that the extra components are part
                        # of the fmri and have been split out because of bad
                        # proxy behaviour.
                        pfmri = "/".join(tokens)
                except IndexError:
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST)

                try:
                        f = fmri.PkgFmri(pfmri, None)
                except fmri.FmriError, e:
                        # If the FMRI couldn't be parsed for whatever reason,
                        # assume the client made a bad request.
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST, str(e))

                m = manifest.Manifest()
                m.set_fmri(None, pfmri)

                try:
                        mpath = os.path.join(self.scfg.pkg_root, f.get_dir_path())
                except fmri.FmriError, e:
                        # If the FMRI operation couldn't be performed, assume
                        # the client made a bad request.
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST, str(e))

                if not os.path.exists(mpath):
                        raise cherrypy.HTTPError(httplib.NOT_FOUND)

                m.set_content(file(mpath).read())

                publisher, name, ver = f.tuple()
                if publisher:
                        publisher = fmri.strip_pub_pfx(publisher)
                else:
                        publisher = "Unknown"
                summary = m.get("description", "")

                lsummary = cStringIO.StringIO()
                for i, entry in enumerate(m.gen_actions_by_type("license")):
                        if i > 0:
                                lsummary.write("\n")

                        lpath = os.path.normpath(os.path.join(
                            self.scfg.file_root,
                            misc.hash_file_name(entry.hash)))

                        lfile = file(lpath, "rb")
                        misc.gunzip_from_stream(lfile, lsummary)
                lsummary.seek(0)

                return """\
          Name: %s
       Summary: %s
     Publisher: %s
       Version: %s
 Build Release: %s
        Branch: %s
Packaging Date: %s
          Size: %s
          FMRI: %s

License:
%s
""" % (name, summary, publisher, ver.release, ver.build_release,
    ver.branch, ver.get_timestamp().ctime(), misc.bytes_to_str(m.size),
    f, lsummary.read())
