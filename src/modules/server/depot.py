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
# Copyright (c) 2008, 2016, Oracle and/or its affiliates. All rights reserved.
#

from __future__ import division

import cherrypy
from cherrypy._cptools import HandlerTool
from cherrypy.lib.static import serve_file
from email.utils import formatdate
from cherrypy.process.plugins import SimplePlugin
from cherrypy._cperror import _HTTPErrorTemplate

try:
        import pybonjour
except (OSError, ImportError):
        pass
else:
        import select

import atexit
import ast
import cStringIO
import errno
import inspect
import itertools
import math
import os
import random
import re
import shutil
import six
import simplejson as json
import socket
import tarfile
import tempfile
import threading
import time

from six.moves import http_client, queue
from six.moves.urllib.parse import quote, urlunsplit

# Without the below statements, tarfile will trigger calls to getpwuid and
# getgrgid for every file downloaded.  This in turn leads to nscd usage which
# limits the throughput of the depot process.  Setting these attributes to
# undefined causes tarfile to skip these calls in tarfile.gettarinfo().  This
# information is unnecesary as it will not be used by the client.
tarfile.pwd = None
tarfile.grp = None

import pkg
import pkg.actions as actions
import pkg.config as cfg
import pkg.fmri as fmri
import pkg.indexer as indexer
import pkg.manifest as manifest
import pkg.misc as misc
import pkg.nrlock
import pkg.p5i as p5i
import pkg.server.face as face
import pkg.server.repository as srepo
import pkg.version

from pkg.server.query_parser import Query, ParseError, BooleanQueryException

class Dummy(object):
        """Dummy object used for dispatch method mapping."""
        pass


class _Depot(object):
        """Private, abstract, base class for all Depot classes."""
        pass


class DepotHTTP(_Depot):
        """The DepotHTTP object is intended to be used as a cherrypy
        application object and represents the set of operations that a
        pkg.depotd server provides to HTTP-based clients."""

        REPO_OPS_DEFAULT = [
            "versions",
            "search",
            "catalog",
            "info",
            "manifest",
            "file",
            "open",
            "append",
            "close",
            "abandon",
            "add",
            "p5i",
            "publisher",
            "index",
            "status",
            "admin",
        ]

        REPO_OPS_READONLY = [
            "versions",
            "search",
            "catalog",
            "info",
            "manifest",
            "file",
            "p5i",
            "publisher",
            "status",
        ]

        REPO_OPS_MIRROR = [
            "versions",
            "file",
            "publisher",
            "status",
        ]

        content_root = None
        web_root = None

        def __init__(self, repo, dconf, request_pub_func=None):
                """Initialize and map the valid operations for the depot.  While
                doing so, ensure that the operations have been explicitly
                "exposed" for external usage.

                request_pub_func, if set is a function that gets called with
                cherrypy.request.path_info that returns the publisher used
                for a given request.
                """

                # This lock is used to protect the depot from multiple
                # threads modifying data structures at the same time.
                self._lock = pkg.nrlock.NRLock()

                self.cfg = dconf
                self.repo = repo
                self.request_pub_func = request_pub_func

                content_root = dconf.get_property("pkg", "content_root")
                pkg_root = dconf.get_property("pkg", "pkg_root")
                if content_root:
                        if not os.path.isabs(content_root):
                                content_root = os.path.join(pkg_root,
                                    content_root)
                        self.content_root = content_root
                        self.web_root = os.path.join(self.content_root, "web")
                else:
                        self.content_root = None
                        self.web_root = None

                # Ensure a temporary storage area exists for depot components
                # to use during operations.
                tmp_root = dconf.get_property("pkg", "writable_root")
                if not tmp_root:
                        # If no writable root, create a temporary area.
                        tmp_root = tempfile.mkdtemp()

                        # Try to ensure temporary area is cleaned up on exit.
                        atexit.register(shutil.rmtree, tmp_root,
                            ignore_errors=True)
                self.tmp_root = tmp_root

                # Handles the BUI (Browser User Interface).
                face.init(self)

                # Store any possible configuration changes.
                repo.write_config()

                if repo.mirror or not repo.root:
                        self.ops_list = self.REPO_OPS_MIRROR[:]
                        if not repo.cfg.get_property("publisher", "prefix"):
                                self.ops_list.remove("publisher")
                elif repo.read_only:
                        self.ops_list = self.REPO_OPS_READONLY
                else:
                        self.ops_list = self.REPO_OPS_DEFAULT

                # Transform the property value into a form convenient
                # for use.
                disable_ops = {}
                for entry in dconf.get_property("pkg", "disable_ops"):
                        if "/" in entry:
                                op, ver = entry.rsplit("/", 1)
                        else:
                                op = entry
                                ver = "*"
                        disable_ops.setdefault(op, [])
                        disable_ops[op].append(ver)

                # Determine available operations and disable as requested.
                self.vops = {}
                for name, func in inspect.getmembers(self, inspect.ismethod):
                        m = re.match("(.*)_(\d+)", name)

                        if not m:
                                continue

                        op = m.group(1)
                        ver = m.group(2)

                        if op not in self.ops_list:
                                continue
                        if op in disable_ops and (ver in disable_ops[op] or
                            "*" in disable_ops[op]):
                                continue
                        if not repo.supports(op, int(ver)):
                                # Unsupported operation.
                                continue

                        func.__dict__["exposed"] = True

                        if op in self.vops:
                                self.vops[op].append(int(ver))
                        else:
                                # We need a Dummy object here since we need to
                                # be able to set arbitrary attributes that
                                # contain function pointers to our object
                                # instance.  CherryPy relies on this for its
                                # dispatch tree mapping mechanism.  We can't
                                # use other object types here since Python
                                # won't let us set arbitary attributes on them.
                                opattr = Dummy()
                                setattr(self, op, opattr)
                                self.vops[op] = [int(ver)]

                                for pub in self.repo.publishers:
                                        pub = pub.replace(".", "_")
                                        pubattr = getattr(self, pub, None)
                                        if not pubattr:
                                                pubattr = Dummy()
                                                setattr(self, pub, pubattr)
                                        setattr(pubattr, op, opattr)

                        opattr = getattr(self, op)
                        setattr(opattr, ver, func)

                cherrypy.config.update({'error_page.default':
                    self.default_error_page})

                if hasattr(cherrypy.engine, "signal_handler"):
                        # This handles SIGUSR1
                        cherrypy.engine.subscribe("graceful", self.refresh)

                # Setup background task execution handler.
                self.__bgtask = BackgroundTaskPlugin(cherrypy.engine)
                self.__bgtask.subscribe()

        def _queue_refresh_index(self):
                """Queues a background task to update search indexes.  This
                method is a protected helper function for depot consumers."""

                try:
                        self.__bgtask.put(self.repo.refresh_index)
                except queue.Full:
                        # If another operation is already in progress, just
                        # log a warning and drive on.
                        cherrypy.log("Skipping indexing; another operation is "
                            "already in progress.", "INDEX")

        @staticmethod
        def default_error_page(**kwargs):
                """This function is registered as the default error page
                for CherryPy errors.  This sets the response headers to
                be uncacheable, and then returns a HTTP response that is
                identical to the default CherryPy message format."""

                response = cherrypy.response
                for key in ('Cache-Control', 'Pragma'):
                        if key in response.headers:
                                del response.headers[key]

                return _HTTPErrorTemplate % kwargs

        def _get_req_pub(self):
                """Private helper function to retrieve the publisher prefix
                for the current operation from the request path.  Returns None
                if a publisher prefix was not found in the request path.  The
                publisher is assumed to be the first component of the path_info
                string if it doesn't match the operation's name.  This does mean
                that a publisher can't be named the same as an operation, but
                that isn't viewed as an unreasonable limitation.
                """

                if self.request_pub_func:
                        return self.request_pub_func(cherrypy.request.path_info)
                try:
                        req_pub = cherrypy.request.path_info.strip("/").split(
                            "/")[0]
                except IndexError:
                        return None

                if req_pub not in self.REPO_OPS_DEFAULT and req_pub != "feed":
                        # Assume that if the first component of the request path
                        # doesn't match a known operation that it's a publisher
                        # prefix.
                        return req_pub
                return None

        def __set_response_expires(self, op_name, expires, max_age=None):
                """Used to set expiration headers on a response dynamically
                based on the name of the operation.

                'op_name' is a string containing the name of the depot
                operation as listed in the REPO_OPS_* constants.

                'expires' is an integer value in seconds indicating how
                long from when the request was made the content returned
                should expire.  The maximum value is 365*86400.

                'max_age' is an integer value in seconds indicating the
                maximum length of time a response should be considered
                valid.  For some operations, the maximum value for this
                parameter is equal to the repository's refresh_seconds
                property."""

                prefix = self._get_req_pub()
                if not prefix:
                        prefix = self.repo.cfg.get_property("publisher",
                            "prefix")

                rs = None
                if prefix:
                        try:
                                pub = self.repo.get_publisher(prefix)
                        except Exception as e:
                                # Couldn't get pub.
                                pass
                        else:
                                repo = pub.repository
                                if repo:
                                        rs = repo.refresh_seconds
                if rs is None:
                        rs = 14400

                if max_age is None:
                        max_age = min((rs, expires))

                now = cherrypy.response.time
                if op_name == "publisher" or op_name == "search" or \
                    op_name == "catalog":
                        # For these operations, cap the value based on
                        # refresh_seconds.
                        expires = now + min((rs, max_age))
                        max_age = min((rs, max_age))
                else:
                        expires = now + expires

                headers = cherrypy.response.headers
                headers["Cache-Control"] = \
                    "must-revalidate, no-transform, max-age={0:d}".format(
                        max_age)
                headers["Expires"] = formatdate(timeval=expires, usegmt=True)

        def refresh(self):
                """Catch SIGUSR1 and reload the depot information."""
                old_pubs = self.repo.publishers
                self.repo.reload()
                if type(self.cfg) == cfg.SMFConfig:
                        # For all other cases, reloading depot configuration
                        # isn't desirable (because of command-line overrides).
                        self.cfg.reset()

                # Handles the BUI (Browser User Interface).
                face.init(self)

                # Map new publishers into operation space.
                map(self.__map_pub_ops, self.repo.publishers - old_pubs)

        def __map_pub_ops(self, pub_prefix):
                # Map the publisher into the depot's operation namespace if
                # needed.
                self._lock.acquire() # Prevent race conditions.
                try:
                        pubattr = getattr(self, pub_prefix, None)
                        if not pubattr:
                                # Might have already been done in
                                # another thread.
                                pubattr = Dummy()
                                setattr(self, pub_prefix, pubattr)

                                for op in self.vops:
                                        opattr = getattr(self, op)
                                        setattr(pubattr, op, opattr)
                finally:
                        self._lock.release()

        @cherrypy.expose
        def default(self, *tokens, **params):
                """Any request that is not explicitly mapped to the repository
                object will be handled by the "externally facing" server
                code instead."""

                pub = self._get_req_pub()
                op = None
                if not pub and tokens:
                        op = tokens[0]
                elif pub and len(tokens) > 1:
                        op = tokens[1]

                if op in self.REPO_OPS_DEFAULT and op not in self.vops:
                        raise cherrypy.HTTPError(http_client.NOT_FOUND,
                            "Operation not supported in current server mode.")
                elif op not in self.vops:
                        request = cherrypy.request
                        response = cherrypy.response
                        if not misc.valid_pub_prefix(pub):
                                pub = None
                        return face.respond(self, request, response, pub)

                # If we get here, we know that 'operation' is supported.
                # Ensure that we have a integer protocol version.
                try:
                        if not pub:
                                ver = int(tokens[1])
                        else:
                                ver = int(tokens[2])
                except IndexError:
                        raise cherrypy.HTTPError(http_client.BAD_REQUEST,
                            "Missing version\n")
                except ValueError:
                        raise cherrypy.HTTPError(http_client.BAD_REQUEST,
                            "Non-integer version\n")

                if ver not in self.vops[op]:
                        # 'version' is not supported for the operation.
                        raise cherrypy.HTTPError(http_client.NOT_FOUND,
                            "Version '{0}' not supported for operation '{1}'\n".format(
                            ver, op))
                elif op == "open" and pub not in self.repo.publishers:
                        if not misc.valid_pub_prefix(pub):
                                raise cherrypy.HTTPError(http_client.BAD_REQUEST,
                                    "Invalid publisher prefix: {0}\n".format(pub))

                        # Map operations for new publisher.
                        self.__map_pub_ops(pub)

                        # Finally, perform an internal redirect so that cherrypy
                        # will correctly redispatch to the newly mapped
                        # operations.
                        rel_uri = cherrypy.request.path_info
                        if cherrypy.request.query_string:
                                rel_uri += "?{0}".format(
                                    cherrypy.request.query_string)
                        raise cherrypy.InternalRedirect(rel_uri)
                elif pub:
                        raise cherrypy.HTTPError(http_client.BAD_REQUEST,
                            "Unknown publisher: {0}\n".format(pub))

                # Assume 'version' is not supported for the operation for some
                # other reason.
                raise cherrypy.HTTPError(http_client.NOT_FOUND, "Version '{0}' not "
                    "supported for operation '{1}'\n".format(ver, op))

        @cherrypy.tools.response_headers(headers=\
            [("Content-Type", "text/plain; charset=utf-8")])
        def versions_0(self, *tokens):
                """Output a text/plain list of valid operations, and their
                versions, supported by the repository."""

                self.__set_response_expires("versions", 5*60, 5*60)
                versions = "pkg-server {0}\n".format(pkg.VERSION)
                versions += "\n".join(
                    "{0} {1}".format(op, " ".join(str(v) for v in vers))
                    for op, vers in six.iteritems(self.vops)
                ) + "\n"
                return versions

        def search_1(self, *args, **params):
                """Based on the request path, return a list of packages that
                match the specified criteria."""
                query_str_lst = []

                # Check for the GET method of doing a search request.
                try:
                        query_str_lst = [args[0]]
                except IndexError:
                        pass

                # Check for the POST method of doing a search request.
                if not query_str_lst:
                        query_str_lst = list(params.values())
                elif list(params.values()):
                        raise cherrypy.HTTPError(http_client.BAD_REQUEST,
                            "args:{0}, params:{1}".format(args, params))

                if not query_str_lst:
                        raise cherrypy.HTTPError(http_client.BAD_REQUEST)

                try:
                        res_list = self.repo.search(query_str_lst,
                            pub=self._get_req_pub())
                except (ParseError, BooleanQueryException) as e:
                        raise cherrypy.HTTPError(http_client.BAD_REQUEST, str(e))
                except srepo.RepositorySearchUnavailableError as e:
                        raise cherrypy.HTTPError(http_client.SERVICE_UNAVAILABLE,
                            str(e))
                except srepo.RepositoryError as e:
                        # Treat any remaining repository error as a 404, but
                        # log the error and include the real failure
                        # information.
                        cherrypy.log("Request failed: {0}".format(str(e)))
                        raise cherrypy.HTTPError(http_client.NOT_FOUND, str(e))

                # In order to be able to have a return code distinguish between
                # no results and search unavailable, we need to use a different
                # http code.  Check and see if there's at least one item in
                # the results.  If not, set the result code to be NO_CONTENT
                # and return.  If there is at least one result, put the result
                # examined back at the front of the results and stream them
                # to the user.
                if len(res_list) == 1:
                        try:
                                tmp = next(res_list[0])
                                res_list = [itertools.chain([tmp], res_list[0])]
                        except StopIteration:
                                cherrypy.response.status = http_client.NO_CONTENT
                                return

                response = cherrypy.response
                response.headers["Content-type"] = "text/plain; charset=utf-8"
                self.__set_response_expires("search", 86400, 86400)

                def output():
                        # Yield the string used to let the client know it's
                        # talking to a valid search server.
                        yield str(Query.VALIDATION_STRING[1])
                        for i, res in enumerate(res_list):
                                for v, return_type, vals in res:
                                        if return_type == Query.RETURN_ACTIONS:
                                                fmri_str, fv, line = vals
                                                yield "{0} {1} {2} {3} {4}\n".format(
                                                    i, return_type, fmri_str,
                                                    quote(fv),
                                                    line.rstrip())
                                        elif return_type == \
                                            Query.RETURN_PACKAGES:
                                                fmri_str = vals
                                                yield "{0} {1} {2}\n".format(
                                                    i, return_type, fmri_str)
                return output()

        search_1._cp_config = { "response.stream": True }

        def catalog_1(self, *tokens):
                """Outputs the contents of the specified catalog file, using the
                name in the request path, directly to the client."""

                try:
                        name = tokens[0]
                except IndexError:
                        raise cherrypy.HTTPError(http_client.FORBIDDEN,
                            _("Directory listing not allowed."))

                try:
                        fpath = self.repo.catalog_1(name,
                            pub=self._get_req_pub())
                except srepo.RepositoryError as e:
                        # Treat any remaining repository error as a 404, but
                        # log the error and include the real failure
                        # information.
                        cherrypy.log("Request failed: {0}".format(str(e)))
                        raise cherrypy.HTTPError(http_client.NOT_FOUND, str(e))

                self.__set_response_expires("catalog", 86400, 86400)
                return serve_file(fpath, "text/plain; charset=utf-8")

        catalog_1._cp_config = { "response.stream": True }

        def manifest_0(self, *tokens):
                """The request is an encoded pkg FMRI.  If the version is
                specified incompletely, we return an error, as the client is
                expected to form correct requests based on its interpretation
                of the catalog and its image policies."""

                try:
                        pubs = self.repo.publishers
                except Exception as e:
                        cherrypy.log("Request failed: {0}".format(e))
                        raise cherrypy.HTTPError(http_client.BAD_REQUEST, str(e))

                # A broken proxy (or client) has caused a fully-qualified FMRI
                # to be split up.
                comps = [t for t in tokens]
                if not comps:
                        raise cherrypy.HTTPError(http_client.FORBIDDEN,
                            _("Directory listing not allowed."))

                if len(comps) > 1 and comps[0] == "pkg:" and comps[1] in pubs:
                        # Only one slash here as another will be added below.
                        comps[0] += "/"

                # Parse request into FMRI component and decode.
                try:
                        # If more than one token (request path component) was
                        # specified, assume that the extra components are part
                        # of the fmri and have been split out because of bad
                        # proxy behaviour.
                        pfmri = "/".join(comps)
                        pfmri = fmri.PkgFmri(pfmri, None)
                        fpath = self.repo.manifest(pfmri,
                            pub=self._get_req_pub())
                except (IndexError, fmri.FmriError) as e:
                        raise cherrypy.HTTPError(http_client.BAD_REQUEST, str(e))
                except srepo.RepositoryError as e:
                        # Treat any remaining repository error as a 404, but
                        # log the error and include the real failure
                        # information.
                        cherrypy.log("Request failed: {0}".format(str(e)))
                        raise cherrypy.HTTPError(http_client.NOT_FOUND, str(e))

                # Send manifest
                self.__set_response_expires("manifest", 86400*365, 86400*365)
                return serve_file(fpath, "text/plain; charset=utf-8")

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


        def file_0(self, *tokens):
                """Outputs the contents of the file, named by the SHA-1 hash
                name in the request path, directly to the client."""

                try:
                        fhash = tokens[0]
                except IndexError:
                        fhash = None

                try:
                        fpath = self.repo.file(fhash, pub=self._get_req_pub())
                except srepo.RepositoryFileNotFoundError as e:
                        raise cherrypy.HTTPError(http_client.NOT_FOUND, str(e))
                except srepo.RepositoryError as e:
                        # Treat any remaining repository error as a 404, but
                        # log the error and include the real failure
                        # information.
                        cherrypy.log("Request failed: {0}".format(str(e)))
                        raise cherrypy.HTTPError(http_client.NOT_FOUND, str(e))

                self.__set_response_expires("file", 86400*365, 86400*365)
                return serve_file(fpath, "application/data")

        file_0._cp_config = { "response.stream": True }

        def file_1(self, *tokens):
                """Outputs the contents of the file, named by the SHA hash
                name in the request path, directly to the client."""

                method = cherrypy.request.method
                if method == "GET":
                        return self.file_0(*tokens)
                elif method in ("POST", "PUT"):
                        return self.__upload_file(*tokens)
                raise cherrypy.HTTPError(http_client.METHOD_NOT_ALLOWED,
                    "{0} is not allowed".format(method))

        # We need to prevent cherrypy from processing the request body so that
        # file can parse the request body itself.  In addition, we also need to
        # set the timeout higher since the default is five minutes; not really
        # enough for a slow connection to upload content.
        file_1._cp_config = {
            "request.process_request_body": False,
            "response.timeout": 3600,
            "response.stream": True
        }

        @cherrypy.tools.response_headers(headers=[("Pragma", "no-cache"),
            ("Cache-Control", "no-cache, no-transform, must-revalidate"),
            ("Expires", 0)])
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
                if not pfmri:
                        raise cherrypy.HTTPError(http_client.BAD_REQUEST,
                            _("A valid package FMRI must be specified."))

                try:
                        pfmri = fmri.PkgFmri(pfmri, client_release)
                        trans_id = self.repo.open(client_release, pfmri)
                except (fmri.FmriError, srepo.RepositoryError) as e:
                        # Assume a bad request was made.  A 404 can't be
                        # returned here as misc.versioned_urlopen will interpret
                        # that to mean that the server doesn't support this
                        # operation.
                        cherrypy.log("Request failed: {0}".format(e))
                        raise cherrypy.HTTPError(http_client.BAD_REQUEST, str(e))

                if pfmri.publisher and not self._get_req_pub():
                        self.__map_pub_ops(pfmri.publisher)

                # Set response headers before returning.
                response.headers["Content-type"] = "text/plain; charset=utf-8"
                response.headers["Transaction-ID"] = trans_id

        @cherrypy.tools.response_headers(headers=[("Pragma", "no-cache"),
            ("Cache-Control", "no-cache, no-transform, must-revalidate"),
            ("Expires", 0)])
        def append_0(self, *tokens):
                """Starts an append transaction for the package name specified
                in the request path.  Returns no output."""

                request = cherrypy.request
                response = cherrypy.response

                client_release = request.headers.get("Client-Release", None)
                try:
                        pfmri = tokens[0]
                except IndexError:
                        pfmri = None

                # XXX Authentication will be handled by virtue of possessing a
                # signed certificate (or a more elaborate system).
                if not pfmri:
                        raise cherrypy.HTTPError(http_client.BAD_REQUEST,
                            _("A valid package FMRI must be specified."))

                try:
                        pfmri = fmri.PkgFmri(pfmri, client_release)
                        trans_id = self.repo.append(client_release, pfmri)
                except (fmri.FmriError, srepo.RepositoryError) as e:
                        # Assume a bad request was made.  A 404 can't be
                        # returned here as misc.versioned_urlopen will interpret
                        # that to mean that the server doesn't support this
                        # operation.
                        cherrypy.log("Request failed: {0}".format(e))
                        raise cherrypy.HTTPError(http_client.BAD_REQUEST, str(e))

                if pfmri.publisher and not self._get_req_pub():
                        self.__map_pub_ops(pfmri.publisher)

                # Set response headers before returning.
                response.headers["Content-type"] = "text/plain; charset=utf-8"
                response.headers["Transaction-ID"] = trans_id

        @cherrypy.tools.response_headers(headers=[("Pragma", "no-cache"),
            ("Cache-Control", "no-cache, no-transform, must-revalidate"),
            ("Expires", 0)])
        def close_0(self, *tokens):
                """Ends an in-flight transaction for the Transaction ID
                specified in the request path.

                Returns a Package-FMRI and State header in the response
                indicating the published FMRI and the state of the package
                in the catalog.  Returns no output."""

                try:
                        # cherrypy decoded it, but we actually need it encoded.
                        trans_id = quote(tokens[0], "")
                except IndexError:
                        trans_id = None

                request = cherrypy.request

                try:
                        # Assume "True" for backwards compatibility.
                        add_to_catalog = int(request.headers.get(
                            "X-IPkg-Add-To-Catalog", 1))

                        # Force a boolean value.
                        if add_to_catalog:
                                add_to_catalog = True
                        else:
                                add_to_catalog = False
                except ValueError as e:
                        raise cherrypy.HTTPError(http_client.BAD_REQUEST,
                            "X-IPkg-Add-To-Catalog".format(e))

                try:
                        pfmri, pstate = self.repo.close(trans_id,
                            add_to_catalog=add_to_catalog)
                except srepo.RepositoryError as e:
                        # Assume a bad request was made.  A 404 can't be
                        # returned here as misc.versioned_urlopen will interpret
                        # that to mean that the server doesn't support this
                        # operation.
                        raise cherrypy.HTTPError(http_client.BAD_REQUEST, str(e))

                response = cherrypy.response
                response.headers["Package-FMRI"] = pfmri
                response.headers["State"] = pstate

        @cherrypy.tools.response_headers(headers=[("Pragma", "no-cache"),
            ("Cache-Control", "no-cache, no-transform, must-revalidate"),
            ("Expires", 0)])
        def admin_0(self, *tokens, **params):
                """Execute a specified repository administration operation based
                on the provided query string.  Example:

                        <repo_uri>[/<publisher>]/admin/0?cmd=refresh-index

                Available commands are:
                        rebuild
                            Discard search data and package catalogs and
                            rebuild both.
                        rebuild-indexes
                            Discard search data and rebuild.
                        rebuild-packages
                            Discard package catalogs and rebuild.
                        refresh
                            Update search and package data.
                        refresh-indexes
                            Update search data.  (Add packages found in the
                            repository to their related search indexes.)
                        refresh-packages
                            Update package data.  (Add packages found in the
                            repository to their related catalog.)
                """

                cmd = params.get("cmd", "")

                # These commands cause the operation requested to be queued
                # for later execution.  This does mean that if the operation
                # fails, the client won't know about it, but this is necessary
                # since these are long running operations (are likely to exceed
                # connection timeout limits).
                try:
                        if cmd == "rebuild":
                                # Discard existing catalog and search data and
                                # rebuild.
                                self.__bgtask.put(self.repo.rebuild,
                                    pub=self._get_req_pub(), build_catalog=True,
                                    build_index=True)
                        elif cmd == "rebuild-indexes":
                                # Discard search data and rebuild.
                                self.__bgtask.put(self.repo.rebuild,
                                    pub=self._get_req_pub(),
                                    build_catalog=False, build_index=True)
                        elif cmd == "rebuild-packages":
                                # Discard package data and rebuild.
                                self.__bgtask.put(self.repo.rebuild,
                                    pub=self._get_req_pub(), build_catalog=True,
                                    build_index=False)
                        elif cmd == "refresh":
                                # Add new packages and update search indexes.
                                self.__bgtask.put(self.repo.add_content,
                                    pub=self._get_req_pub(), refresh_index=True)
                        elif cmd == "refresh-indexes":
                                # Update search indexes.
                                self.__bgtask.put(self.repo.refresh_index,
                                    pub=self._get_req_pub())
                        elif cmd == "refresh-packages":
                                # Add new packages.
                                self.__bgtask.put(self.repo.add_content,
                                    pub=self._get_req_pub(),
                                    refresh_index=False)
                        else:
                                raise cherrypy.HTTPError(http_client.BAD_REQUEST,
                                   "Unknown or unsupported operation: '{0}'".format(
                                   cmd))
                except queue.Full:
                        raise cherrypy.HTTPError(http_client.SERVICE_UNAVAILABLE,
                           "Another operation is already in progress; try "
                           "again later.")

        @cherrypy.tools.response_headers(headers=[("Pragma", "no-cache"),
            ("Cache-Control", "no-cache, no-transform, must-revalidate"),
            ("Expires", 0)])
        def abandon_0(self, *tokens):
                """Aborts an in-flight transaction for the Transaction ID
                specified in the request path.  Returns no output."""

                try:
                        # cherrypy decoded it, but we actually need it encoded.
                        trans_id = quote(tokens[0], "")
                except IndexError:
                        trans_id = None

                try:
                        self.repo.abandon(trans_id)
                except srepo.RepositoryError as e:
                        # Assume a bad request was made.  A 404 can't be
                        # returned here as misc.versioned_urlopen will interpret
                        # that to mean that the server doesn't support this
                        # operation.
                        raise cherrypy.HTTPError(http_client.BAD_REQUEST, str(e))

        def add_0(self, *tokens):
                """Adds an action and its content to an in-flight transaction
                for the Transaction ID specified in the request path.  The
                content is expected to be in the request body.  Returns no
                output."""

                try:
                        # cherrypy decoded it, but we actually need it encoded.
                        trans_id = quote(tokens[0], "")
                except IndexError:
                        trans_id = None

                try:
                        entry_type = tokens[1]
                except IndexError:
                        entry_type = None

                if entry_type not in actions.types:
                        raise cherrypy.HTTPError(http_client.BAD_REQUEST, _("The "
                            "specified Action Type, '{0}', is not valid.").format(
                            entry_type))

                request = cherrypy.request
                attrs = dict(
                    val.split("=", 1)
                    for hdr, val in request.headers.items()
                    if hdr.lower().startswith("x-ipkg-setattr")
                )

                # If any attributes appear to be lists, make them lists.
                for a in attrs:
                        if attrs[a].startswith("[") and attrs[a].endswith("]"):
                                # Ensure input is valid; only a list will be
                                # accepted.
                                try:
                                        val = ast.literal_eval(attrs[a])
                                        if not isinstance(val, list):
                                                raise ValueError()
                                        attrs[a] = val
                                except ValueError:
                                        raise cherrypy.HTTPError(
                                            http_client.BAD_REQUEST, _("The "
                                            "specified Action attribute value, "
                                            "'{0}', is not valid.").format(
                                            attrs[a]))

                data = None
                size = int(request.headers.get("Content-Length", 0))
                if size > 0:
                        data = request.rfile
                        # Record the size of the payload, if there is one.
                        attrs["pkg.size"] = str(size)

                try:
                        action = actions.types[entry_type](data, **attrs)
                except actions.ActionError as e:
                        cherrypy.log("Request failed: {0}".format(str(e)))
                        raise cherrypy.HTTPError(http_client.BAD_REQUEST, str(e))

                # XXX Once actions are labelled with critical nature.
                # if entry_type in critical_actions:
                #         self.critical = True

                try:
                        self.repo.add(trans_id, action)
                except srepo.RepositoryError as e:
                        # Assume a bad request was made.  A 404 can't be
                        # returned here as misc.versioned_urlopen will interpret
                        # that to mean that the server doesn't support this
                        # operation.
                        cherrypy.log("Request failed: {0}".format(str(e)))
                        raise cherrypy.HTTPError(http_client.BAD_REQUEST, str(e))

        # We need to prevent cherrypy from processing the request body so that
        # add can parse the request body itself.  In addition, we also need to
        # set the timeout higher since the default is five minutes; not really
        # enough for a slow connection to upload content.
        add_0._cp_config = {
            "request.process_request_body": False,
            "response.timeout": 3600,
            "tools.response_headers.on": True,
            "tools.response_headers.headers": [
                ("Pragma", "no-cache"),
                ("Cache-Control", "no-cache, no-transform, must-revalidate"),
                ("Expires", 0)
            ]
        }

        def __upload_file(self, *tokens):
                """Adds a file to an in-flight transaction for the Transaction
                ID specified in the request path.  The content is expected to be
                in the request body.  Returns no output."""

                try:
                        # cherrypy decoded it, but we actually need it encoded.
                        trans_id = quote(tokens[0], "")
                except IndexError:
                        raise
                        trans_id = None

                request = cherrypy.request
                response = cherrypy.response

                size = int(request.headers.get("Content-Length", 0))
                if size < 0:
                        raise cherrypy.HTTPError(http_client.BAD_REQUEST,
                            _("file/1 must be sent a file."))
                data = request.rfile

                try:
                        self.repo.add_file(trans_id, data, size)
                except srepo.RepositoryError as e:
                        # Assume a bad request was made.  A 404 can't be
                        # returned here as misc.versioned_urlopen will interpret
                        # that to mean that the server doesn't support this
                        # operation.
                        raise cherrypy.HTTPError(http_client.BAD_REQUEST, str(e))
                response.headers["Content-Length"] = "0"
                return response.body

        @cherrypy.tools.response_headers(headers=[("Pragma", "no-cache"),
            ("Cache-Control", "no-cache, no-transform, must-revalidate"),
            ("Expires", 0)])
        def index_0(self, *tokens):
                """Provides an administrative interface for search indexing.
                Returns no output if successful; otherwise the response body
                will contain the failure details.
                """

                try:
                        cmd = tokens[0]
                except IndexError:
                        cmd = ""

                # These commands cause the operation requested to be queued
                # for later execution.  This does mean that if the operation
                # fails, the client won't know about it, but this is necessary
                # since these are long running operations (are likely to exceed
                # connection timeout limits).
                try:
                        if cmd == "refresh":
                                # Update search indexes.
                                self.__bgtask.put(self.repo.refresh_index,
                                    pub=self._get_req_pub())
                        else:
                                err = "Unknown index subcommand: {0}".format(
                                    cmd)
                                cherrypy.log(err)
                                raise cherrypy.HTTPError(http_client.NOT_FOUND, err)
                except queue.Full:
                        raise cherrypy.HTTPError(http_client.SERVICE_UNAVAILABLE,
                           "Another operation is already in progress; try "
                           "again later.")

        @cherrypy.tools.response_headers(headers=\
            [("Content-Type", "text/plain; charset=utf-8")])
        def info_0(self, *tokens):
                """ Output a text/plain summary of information about the
                    specified package. The request is an encoded pkg FMRI.  If
                    the version is specified incompletely, we return an error,
                    as the client is expected to form correct requests, based
                    on its interpretation of the catalog and its image
                    policies. """

                try:
                        pubs = self.repo.publishers
                except Exception as e:
                        cherrypy.log("Request failed: {0}".format(e))
                        raise cherrypy.HTTPError(http_client.BAD_REQUEST, str(e))

                # A broken proxy (or client) has caused a fully-qualified FMRI
                # to be split up.
                comps = [t for t in tokens]
                if len(comps) > 1 and comps[0] == "pkg:" and comps[1] in pubs:
                        # Only one slash here as another will be added below.
                        comps[0] += "/"

                # Parse request into FMRI component and decode.
                try:
                        # If more than one token (request path component) was
                        # specified, assume that the extra components are part
                        # of the fmri and have been split out because of bad
                        # proxy behaviour.
                        pfmri = "/".join(comps)
                        pfmri = fmri.PkgFmri(pfmri, None)
                        pub = self._get_req_pub()
                        if not pfmri.publisher:
                                if not pub:
                                        pub = self.repo.cfg.get_property(
                                            "publisher", "prefix")
                                if pub:
                                        pfmri.publisher = pub
                        fpath = self.repo.manifest(pfmri, pub=pub)
                except (IndexError, fmri.FmriError) as e:
                        raise cherrypy.HTTPError(http_client.BAD_REQUEST, str(e))
                except srepo.RepositoryError as e:
                        # Treat any remaining repository error as a 404, but
                        # log the error and include the real failure
                        # information.
                        cherrypy.log("Request failed: {0}".format(str(e)))
                        raise cherrypy.HTTPError(http_client.NOT_FOUND, str(e))

                if not os.path.exists(fpath):
                        raise cherrypy.HTTPError(http_client.NOT_FOUND)

                m = manifest.Manifest(pfmri)
                m.set_content(pathname=fpath)

                pub, name, ver = pfmri.tuple()
                summary = m.get("pkg.summary", m.get("description", ""))

                lsummary = cStringIO.StringIO()
                for i, entry in enumerate(m.gen_actions_by_type("license")):
                        if i > 0:
                                lsummary.write("\n")
                        try:
                                lpath = self.repo.file(entry.hash, pub=pub)
                        except srepo.RepositoryFileNotFoundError:
                                # Skip the license.
                                continue

                        with open(lpath, "rb") as lfile:
                                misc.gunzip_from_stream(lfile, lsummary,
                                    ignore_hash=True)
                lsummary.seek(0)

                self.__set_response_expires("info", 86400*365, 86400*365)
                size, csize = m.get_size()

                # Add human version if exist.
                hum_ver = m.get("pkg.human-version", "")
                version = ver.release
                if hum_ver and hum_ver != str(ver.release):
                        version = "{0} ({1})".format(ver.release, hum_ver)
                return """\
           Name: {0}
        Summary: {1}
      Publisher: {2}
        Version: {3}
  Build Release: {4}
         Branch: {5}
 Packaging Date: {6}
           Size: {7}
Compressed Size: {8}
           FMRI: {9}

License:
{10}
""".format(name, summary, pub, version, ver.build_release,
    ver.branch, ver.get_timestamp().strftime("%c"), misc.bytes_to_str(size),
    misc.bytes_to_str(csize), pfmri, lsummary.read())

        @cherrypy.tools.response_headers(headers=[(
            "Content-Type", p5i.MIME_TYPE)])
        def publisher_0(self, *tokens):
                """Returns a pkg(5) information datastream based on the
                repository configuration's publisher information."""

                prefix = self._get_req_pub()
                pubs = [
                   pub for pub in self.repo.get_publishers()
                   if not prefix or pub.prefix == prefix
                ]
                if prefix and not pubs:
                        # Publisher specified in request is unknown.
                        e = srepo.RepositoryUnknownPublisher(prefix)
                        cherrypy.log("Request failed: {0}".format(str(e)))
                        raise cherrypy.HTTPError(http_client.NOT_FOUND, str(e))

                buf = cStringIO.StringIO()
                try:
                        p5i.write(buf, pubs)
                except Exception as e:
                        # Treat any remaining error as a 404, but log it and
                        # include the real failure information.
                        cherrypy.log("Request failed: {0}".format(str(e)))
                        raise cherrypy.HTTPError(http_client.NOT_FOUND, str(e))
                buf.seek(0)
                self.__set_response_expires("publisher", 86400*365, 86400*365)
                return buf.getvalue()

        @cherrypy.tools.response_headers(headers=[(
            "Content-Type", p5i.MIME_TYPE)])
        def publisher_1(self, *tokens):
                """Returns a pkg(5) information datastream based on the
                the request's publisher or all if not specified."""

                prefix = self._get_req_pub()

                pubs = []
                if not prefix:
                        pubs = self.repo.get_publishers()
                else:
                        try:
                                pub = self.repo.get_publisher(prefix)
                                pubs.append(pub)
                        except Exception as e:
                                # If the Publisher object creation fails, return
                                # a not found error to the client so it will
                                # treat it as an unsupported operation.
                                cherrypy.log("Request failed: {0}".format(
                                    str(e)))
                                raise cherrypy.HTTPError(http_client.NOT_FOUND,
                                    str(e))

                buf = cStringIO.StringIO()
                try:
                        p5i.write(buf, pubs)
                except Exception as e:
                        # Treat any remaining error as a 404, but log it and
                        # include the real failure information.
                        cherrypy.log("Request failed: {0}".format(str(e)))
                        raise cherrypy.HTTPError(http_client.NOT_FOUND, str(e))
                buf.seek(0)
                self.__set_response_expires("publisher", 86400*365, 86400*365)
                return buf.getvalue()

        def __get_matching_p5i_data(self, rstore, pfmri):
                # Attempt to find matching entries in the catalog.
                try:
                        pub = self.repo.get_publisher(rstore.publisher)
                except srepo.RepositoryUnknownPublisher:
                        return ""

                try:
                        cat = rstore.catalog
                except (srepo.RepositoryMirrorError,
                    srepo.RepositoryUnsupportedOperationError):
                        return ""

                try:
                        matches = [fmri for fmri, states, attrs in \
                            cat.gen_packages(patterns=[pfmri],
                            return_fmris=True)]

                except Exception as e:
                        # If this fails, it's ok to raise an exception since bad
                        # input was likely provided.
                        cherrypy.log("Request failed: {0}".format(e))
                        raise cherrypy.HTTPError(http_client.BAD_REQUEST, str(e))

                if not matches:
                        return ""

                if not "@" in pfmri or "*" in pfmri:
                        # When using wildcards or exact name match, trim the
                        # results to only the unique package stems.
                        matches = sorted(set([m.pkg_name for m in matches]))
                else:
                        # Ensure all fmris are output without publisher prefix
                        # and without scheme.
                        matches = [
                            m.get_fmri(anarchy=True, include_scheme=False)
                            for m in matches
                        ]

                buf = cStringIO.StringIO()
                pkg_names = { pub.prefix: matches }
                p5i.write(buf, [pub], pkg_names=pkg_names)
                buf.seek(0)
                return buf.getvalue()

        @cherrypy.tools.response_headers(headers=[(
            "Content-Type", p5i.MIME_TYPE)])
        def p5i_0(self, *tokens):
                """Returns a pkg(5) information datastream for the provided full
                or partial FMRI using the repository configuration's publisher
                information.  If a partial FMRI is specified, an attempt to
                validate it will be made, and it will be put into the p5i
                datastream as provided."""

                try:
                        pubs = self.repo.publishers
                except Exception as e:
                        cherrypy.log("Request failed: {0}".format(e))
                        raise cherrypy.HTTPError(http_client.BAD_REQUEST, str(e))

                # A broken proxy (or client) has caused a fully-qualified FMRI
                # to be split up.
                comps = [t for t in tokens]
                if len(comps) > 1 and comps[0] == "pkg:" and comps[1] in pubs:
                        # Only one slash here as another will be added below.
                        comps[0] += "/"

                try:
                        # If more than one token (request path component) was
                        # specified, assume that the extra components are part
                        # of an FMRI and have been split out because of bad
                        # proxy behaviour.
                        pfmri = "/".join(comps)
                except IndexError:
                        raise cherrypy.HTTPError(http_client.BAD_REQUEST)

                # XXX This is a hack to deal with the fact that packagemanager
                # brokenly expects all p5i URIs or files to have a .p5i
                # extension instead of just relying on the api to parse it.
                # This hack allows callers to append a .p5i extension to the
                # URI without affecting the operation.
                if pfmri.endswith(".p5i"):
                        end = len(pfmri) - len(".p5i")
                        pfmri = pfmri[:end]

                output = ""
                prefix = self._get_req_pub()
                for rstore in self.repo.rstores:
                        if not rstore.publisher:
                                continue
                        if prefix and prefix != rstore.publisher:
                                continue
                        output += self.__get_matching_p5i_data(rstore, pfmri)

                if output == "":
                        raise cherrypy.HTTPError(http_client.NOT_FOUND, _("No "
                            "matching package found in repository."))

                self.__set_response_expires("p5i", 86400*365, 86400*365)
                return output

        @cherrypy.tools.response_headers(headers=\
            [("Content-Type", "application/json; charset=utf-8")])
        def status_0(self, *tokens):
                """Return a JSON formatted dictionary containing statistics
                information for the repository being served."""

                self.__set_response_expires("versions", 5*60, 5*60)

                dump_struct = self.repo.get_status()

                try:
                        out = json.dumps(dump_struct, ensure_ascii=False,
                            indent=2, sort_keys=True)
                except Exception as e:
                        raise cherrypy.HTTPError(http_client.NOT_FOUND, _("Unable "
                            "to generate statistics."))
                return out + "\n"

def nasty_before_handler(nasty_depot, maxroll=100):
        """Cherrypy Tool callable which generates various problems prior to a
        request.  Possible outcomes: retryable HTTP error, short nap."""

        # Must be set in _cp_config on associated request handler.
        assert nasty_depot

        # Adjust nastiness values once per incoming request.
        nasty_depot.nasty_housekeeping()

        # Just roll the main nasty dice once.
        if not nasty_depot.need_nasty(maxroll=maxroll):
                return False

        while True:
                roll = random.randint(0, 10)
                if roll == 0:
                        nasty_depot.nasty_nap()
                        if random.randint(0, 1) == 1:
                                # Nap was enough. Let the normal handler run.
                                return False
                if 1 <= roll <= 8:
                        nasty_depot.nasty_raise_error()
                else:
                        cherrypy.log("NASTY: return bogus or empty response")
                        response = cherrypy.response
                        response.body = random.choice(['',
                            'set this is a bogus action',
                            'Instead of office chair, '
                                'package contained bobcat.',
                            '{"this is a": "fragment of json"}'])
                        return True
        return False


class NastyDepotHTTP(DepotHTTP):
        """A class that creates a depot that misbehaves.  Naughty
        depots are useful for testing."""

        # Nastiness ebbs and flows in a sinusoidal NASTY_CYCLE length pattern.
        # The magnitude of the effect is governed by NASTY_MULTIPLIER.
        # See also nasty_housekeeping().
        NASTY_CYCLE = 200
        NASTY_MULTIPLIER = 1.0

        def __init__(self, repo, dconf):
                """Initialize."""

                DepotHTTP.__init__(self, repo, dconf)

                # Handles the BUI (Browser User Interface).
                face.init(self)

                # Store any possible configuration changes.
                self.repo.write_config()

                self.requested_files = []
                self.requested_catalogs = []
                self.requested_manifests = []

                self.nasty_level = \
                    int(dconf.get_property("nasty", "nasty_level"))
                self.nasty_sleep = \
                    int(dconf.get_property("nasty", "nasty_sleep"))

                self.nasty_cycle = self.NASTY_CYCLE
                self.maxroll_adj = 1.0

                cherrypy.log("NASTY Depot Started")
                cherrypy.log("NASTY nasty={0:d}, nasty_sleep={1:d}".format(
                    self.nasty_level, self.nasty_sleep))

                # See CherryPy HandlerTool docs; this sets up a special
                # tool which can prevent the main request body from running
                # when needed.
                cherrypy.tools.nasty_before = HandlerTool(nasty_before_handler)

                self._cp_config = {
                    # Turn on this tool for all requests.
                    'tools.nasty_before.on': True,
                    #
                    # This is tricky: we poke a reference to ourself into our
                    # own _cp_config, specifically so that we can get this
                    # reference passed by cherrypy as an input argument to our
                    # nasty_before tool, so that it can in turn call methods
                    # back on this object.
                    #
                    'tools.nasty_before.nasty_depot': self
                }

                # Set up a list of errors that we can pick from when we
                # want to return an error at random to the client.  Errors
                # are weighted by how often we want them to happen; the loop
                # below then puts them into a pick-list.
                errors = {
                    http_client.REQUEST_TIMEOUT: 10,
                    http_client.BAD_GATEWAY: 10,
                    http_client.GATEWAY_TIMEOUT: 10,
                    http_client.FORBIDDEN: 2,
                    http_client.NOT_FOUND: 2,
                    http_client.BAD_REQUEST: 2
                }

                self.errlist = []
                for x, n in six.iteritems(errors):
                        for i in range(0, n):
                                self.errlist.append(x)
                cherrypy.log("NASTY Depot Error List: {0}".format(
                    str(self.errlist)))

        def nasty_housekeeping(self):
                # Generate a sine wave (well, half of one) which is NASTY_CYCLE
                # steps long and use that to increase maxroll (thus reducing
                # the nastiness).  The causes nastiness to come and go in
                # waves, which helps to prevent excessive nastiness from
                # impeding all progress.
                #
                # The intention is for this to get adjusted once per request.

                # Prevent races updating global nastiness information.
                # Note that this isn't strictly necessary since nasty_cycle
                # and maxroll_adj are just numbers and races are essentially
                # harmless, but this is here so that we don't screw things up
                # in the future.
                self._lock.acquire()

                self.nasty_cycle = (self.nasty_cycle + 1) % self.NASTY_CYCLE
                # old-division; pylint: disable=W1619
                self.maxroll_adj = 1 + self.NASTY_MULTIPLIER * \
                    math.sin(self.nasty_cycle *
                        (math.pi / self.NASTY_CYCLE))
                if self.nasty_cycle == 0:
                        cherrypy.log("NASTY nastiness at min")
                if self.nasty_cycle == self.NASTY_CYCLE // 2:
                        cherrypy.log("NASTY nastiness at max")

                self._lock.release()

        def need_nasty(self, maxroll=100):
                """Randomly returns true when the server should misbehave."""

                # Apply the sine wave adjustment to maxroll-- preserving the
                # possiblity that bad things can still sporadically happen.
                # n.b. we don't bother to pick up the lock here.
                maxroll = int(maxroll * self.maxroll_adj)

                roll = random.randint(1, maxroll)
                if roll <= self.nasty_level:
                        return True
                return False

        def need_nasty_2(self):
                """Nastiness sometimes."""
                return self.need_nasty(maxroll=500)

        def need_nasty_3(self):
                """Nastiness less often."""
                return self.need_nasty(maxroll=2000)

        def need_nasty_4(self):
                """Nastiness very rarely."""
                return self.need_nasty(maxroll=20000)

        def nasty_raise_error(self):
                """Raise an http error from self.errlist."""
                code = random.choice(self.errlist)
                cherrypy.log("NASTY: Random HTTP error: {0:d}".format(code))
                raise cherrypy.HTTPError(code)

        def nasty_nap(self):
                """Sleep for a few seconds."""
                cherrypy.log("NASTY: sleep for {0:d} secs".format(
                    self.nasty_sleep))
                time.sleep(self.nasty_sleep)

        @cherrypy.expose
        def nasty(self, *tokens):
                try:
                        nasty_level = int(tokens[0])
                except (IndexError, ValueError):
                        raise cherrypy.HTTPError(http_client.BAD_REQUEST)
                if nasty_level < 0 or nasty_level > 100:
                        raise cherrypy.HTTPError(http_client.BAD_REQUEST)
                cherrypy.log("Nastiness set to {0:d} by client request".format(
                    nasty_level))
                self.nasty_level = nasty_level

        # Disable the before handler for this request.
        nasty._cp_config = { "tools.nasty_before.on": False }

        @cherrypy.tools.response_headers(headers=\
            [("Content-Type", "text/plain; charset=utf-8")])
        def versions_0(self, *tokens):
                """Output a text/plain list of valid operations, and their
                versions, supported by the repository."""

                # NASTY
                # emit an X-Ipkg-Error HTTP unauthorized response.
                if self.need_nasty_3():
                        cherrypy.log("NASTY versions_0: X-Ipkg-Error")
                        response = cherrypy.response
                        response.status = http_client.UNAUTHORIZED
                        response.headers["X-Ipkg-Error"] = random.choice(["ENT",
                            "LIC", "SVR", "MNT", "YYZ", ""])
                        return ""

                # NASTY
                # Serve up versions header but no versions
                if self.need_nasty_3():
                        cherrypy.log("NASTY versions_0: header but no versions")
                        versions = "pkg-server {0}\n".format(pkg.VERSION)
                        return versions

                # NASTY
                # Serve up bogus versions by adding/subtracting from
                # the actual version numbers-- we use a normal distribution
                # to keep the perturbations small.
                if self.need_nasty_2():
                        cherrypy.log("NASTY versions_0: modified version #s")
                        versions = "pkg-server {0}-nasty\n".format(pkg.VERSION)
                        for op, vers in six.iteritems(self.vops):
                                versions += op + " "
                                verlen = len(vers)
                                for v in vers:
                                        # if there are multiple versions,
                                        # then sometimes leave one out
                                        if verlen > 1 and \
                                            random.randint(0, 10) <= 1:
                                                cherrypy.log(
                                                    "NASTY versions_0: "
                                                    "dropped {0}/{1}".format(op,
                                                    v))
                                                verlen -= 1
                                                continue
                                        # Periodically increment or
                                        # decrement the version.
                                        oldv = v
                                        v = int(v +
                                            random.normalvariate(0, 0.8))
                                        versions += str(v) + " "
                                        if v != oldv:
                                                cherrypy.log(
                                                    "NASTY versions_0: "
                                                    "Altered {0}/{1} -> {2}/{3:d}".format(
                                                    op, oldv, op, v))
                                versions += "\n"
                        return versions

                versions = "pkg-server {0}\n".format(pkg.VERSION)
                versions += "\n".join(
                    "{0} {1}".format(op, " ".join(str(v) for v in vers))
                    for op, vers in six.iteritems(self.vops)
                ) + "\n"
                return versions

        # Fire the before handler less often for versions/0; when it
        # fails everything else comes to a halt.
        versions_0._cp_config = { "tools.nasty_before.maxroll": 200 }

        def manifest_0(self, *tokens):
                """The request is an encoded pkg FMRI.  If the version is
                specified incompletely, we return an error, as the client is
                expected to form correct requests based on its interpretation
                of the catalog and its image policies."""

                try:
                        pubs = self.repo.publishers
                except Exception as e:
                        cherrypy.log("Request failed: {0}".format(e))
                        raise cherrypy.HTTPError(http_client.BAD_REQUEST, str(e))

                # A broken proxy (or client) has caused a fully-qualified FMRI
                # to be split up.
                comps = [t for t in tokens]
                if not comps:
                        raise cherrypy.HTTPError(http_client.FORBIDDEN,
                            _("Directory listing not allowed."))

                if len(comps) > 1 and comps[0] == "pkg:" and comps[1] in pubs:
                        # Only one slash here as another will be added below.
                        comps[0] += "/"

                # Parse request into FMRI component and decode.
                try:
                        # If more than one token (request path component) was
                        # specified, assume that the extra components are part
                        # of the fmri and have been split out because of bad
                        # proxy behaviour.
                        pfmri = "/".join(comps)
                        pfmri = fmri.PkgFmri(pfmri, None)
                        fpath = self.repo.manifest(pfmri,
                            pub=self._get_req_pub())
                except (IndexError, fmri.FmriError) as e:
                        raise cherrypy.HTTPError(http_client.BAD_REQUEST, str(e))
                except srepo.RepositoryError as e:
                        # Treat any remaining repository error as a 404, but
                        # log the error and include the real failure
                        # information.
                        cherrypy.log("Request failed: {0}".format(str(e)))
                        raise cherrypy.HTTPError(http_client.NOT_FOUND, str(e))

                # NASTY
                # Stash manifest entry for later use.
                # Toss out the list if it's larger than 1024 items.
                if len(self.requested_manifests) > 1024:
                        self.requested_manifests = [fpath]
                else:
                        self.requested_manifests.append(fpath)

                # NASTY
                # Send the wrong manifest
                if self.need_nasty_3():
                        cherrypy.log("NASTY manifest_0: serve wrong mfst")
                        badpath = random.choice(self.requested_manifests)
                        return serve_file(badpath, "text/plain; charset=utf-8")

                # NASTY
                # Call a misbehaving serve_file
                return self.nasty_serve_file(fpath, "text/plain; charset=utf-8")

        manifest_0._cp_config = {
            "response.stream": True,
            "tools.nasty_before.maxroll": 200
        }

        def __get_bad_path(self, v):
                fpath = self.repo.file(v, pub=self._get_req_pub())
                return os.path.join(os.path.dirname(fpath), fpath)

        def file_0(self, *tokens):
                """Outputs the contents of the file, named by the SHA-1 hash
                name in the request path, directly to the client."""

                try:
                        fhash = tokens[0]
                except IndexError:
                        fhash = None

                try:
                        fpath = self.repo.file(fhash, pub=self._get_req_pub())
                except srepo.RepositoryFileNotFoundError as e:
                        raise cherrypy.HTTPError(http_client.NOT_FOUND, str(e))
                except srepo.RepositoryError as e:
                        # Treat any remaining repository error as a 404, but
                        # log the error and include the real failure
                        # information.
                        cherrypy.log("Request failed: {0}".format(str(e)))
                        raise cherrypy.HTTPError(http_client.NOT_FOUND, str(e))

                # NASTY
                # Stash filename for later use.
                # Toss out the list if it's larger than 1024 items.
                if len(self.requested_files) > 1024:
                        self.requested_files = [fhash]
                else:
                        self.requested_files.append(fhash)

                # NASTY
                if self.need_nasty_4():
                        # Forget that the file is here
                        cherrypy.log("NASTY file_0: 404 NOT_FOUND")
                        raise cherrypy.HTTPError(http_client.NOT_FOUND)

                # NASTY
                # Send the wrong file
                if self.need_nasty_4():
                        cherrypy.log("NASTY file_0: serve wrong file")
                        badfn = random.choice(self.requested_files)
                        badpath = self.__get_bad_path(badfn)

                        return serve_file(badpath, "application/data")

                # NASTY
                # Call a misbehaving serve_file
                return self.nasty_serve_file(fpath, "application/data")

        file_0._cp_config = { "response.stream": True }

        # file_1 degenerates to calling file_0 except when publishing, so
        # there's no need to touch it here.

        def catalog_1(self, *tokens):
                """Outputs the contents of the specified catalog file, using the
                name in the request path, directly to the client."""

                try:
                        name = tokens[0]
                except IndexError:
                        raise cherrypy.HTTPError(http_client.FORBIDDEN,
                            _("Directory listing not allowed."))

                try:
                        fpath = self.repo.catalog_1(name,
                            pub=self._get_req_pub())
                except srepo.RepositoryError as e:
                        # Treat any remaining repository error as a 404, but
                        # log the error and include the real failure
                        # information.
                        cherrypy.log("Request failed: {0}".format(str(e)))
                        raise cherrypy.HTTPError(http_client.NOT_FOUND, str(e))

                # NASTY
                # Stash catalog entry for later use.
                # Toss out the list if it's larger than 1024 items.
                if len(self.requested_catalogs) > 1024:
                        self.requested_catalogs = [fpath]
                else:
                        self.requested_catalogs.append(fpath)

                # NASTY
                # Send the wrong catalog
                if self.need_nasty_3():
                        cherrypy.log("NASTY catalog_1: wrong catalog file")
                        badpath = random.choice(self.requested_catalogs)
                        return serve_file(badpath, "text/plain; charset=utf-8")

                # NASTY
                return self.nasty_serve_file(fpath, "text/plain; charset=utf-8")

        catalog_1._cp_config = {
            "response.stream": True,
            "tools.nasty_before.maxroll": 200
        }

        def search_1(self, *args, **params):
                # Raise assorted errors; if not, call superclass search_1.
                if self.need_nasty():
                        errs = [http_client.NOT_FOUND, http_client.BAD_REQUEST,
                            http_client.SERVICE_UNAVAILABLE]
                        code = random.choice(errs)
                        cherrypy.log("NASTY search_1: HTTP {0:d}".format(code))
                        raise cherrypy.HTTPError(code)

                return DepotHTTP.search_1(self, *args, **params)

        def nasty_serve_file(self, filepath, content_type):
                """A method that imitates the functionality of serve_file(),
                but behaves in a nasty manner."""

                already_nasty = False

                response = cherrypy.response
                response.headers["Content-Type"] = content_type
                try:
                        fst = os.stat(filepath)
                        filesz = fst.st_size
                        nfile = open(filepath, "rb")
                except EnvironmentError:
                        raise cherrypy.HTTPError(http_client.NOT_FOUND)

                # NASTY
                # Send incorrect content length
                if self.need_nasty_4():
                        response.headers["Content-Length"] = str(filesz +
                                random.randint(1, 1024))
                        already_nasty = True
                else:
                        response.headers["Content-Length"] = str(filesz)

                if already_nasty:
                        response.body = nfile.read(filesz)
                elif self.need_nasty_3():
                        # NASTY
                        # Send truncated file
                        cherrypy.log("NASTY serve_file: truncated file")
                        response.body = nfile.read(filesz - random.randint(1,
                            filesz - 1))
                        # If we're sending data, lie about the length and
                        # make the client catch us.
                        if content_type == "application/data":
                                response.headers["Content-Length"] = str(
                                    len(response.body))
                elif self.need_nasty_3():
                        # NASTY
                        # Write garbage into the response
                        cherrypy.log("NASTY serve_file: prepend garbage")
                        response.body = "NASTY!"
                        response.body += nfile.read(filesz)
                        # If we're sending data, lie about the length and
                        # make the client catch us.
                        if content_type == "application/data":
                                response.headers["Content-Length"] = str(
                                    len(response.body))
                elif self.need_nasty_3():
                        # NASTY
                        # overwrite some garbage into the response, without
                        # changing the length.
                        cherrypy.log("NASTY serve_file: flip bits")
                        body = nfile.read(filesz)
                        # pick a low number of bytes to corrupt
                        ncorrupt = 1 + int(abs(random.gauss(0, 1)))
                        for x in range(0, ncorrupt):
                                p = random.randint(0, max(0, filesz - 1))
                                char = ord(body[p])
                                # pick a bit to flip; favor low numbers, must
                                # also cap at bit #7.
                                bit = min(7, int(abs(random.gauss(0, 3))))
                                # flip it
                                char ^= (1 << bit)
                                body = body[:p] + chr(char) + body[p + 1:]
                        response.body = body
                else:
                        response.body = nfile.read(filesz)

                return response.body


class DNSSD_Plugin(SimplePlugin):
        """Allow a depot to configure DNS-SD through mDNS."""

        def __init__(self, bus, gconf):
                """Bus is the cherrypy engine and gconf is a dictionary
                containing the CherryPy configuration.
                """

                SimplePlugin.__init__(self, bus)

                if "pybonjour" not in globals():
                        self.start = lambda: None
                        self.exit = lambda: None
                        return

                self.name = "pkg(5) mirror on {0}".format(socket.gethostname())
                self.wanted_name = self.name
                self.regtype = "_pkg5._tcp"
                self.port = gconf["server.socket_port"]
                self.sd_hdl = None
                self.reg_ok = False

                if gconf["server.ssl_certificate"] and \
                    gconf["server.ssl_private_key"]:
                        proto = "https"
                else:
                        proto = "http"

                netloc = "{0}:{1}".format(socket.getfqdn(), self.port)
                self.url = urlunsplit((proto, netloc, '', '', ''))

        def reg_cb(self, sd_hdl, flags, error_code, name, regtype, domain):
                """Callback invoked by service register function.  Arguments
                are determined by the pybonjour framework, and must not
                be changed.
                """

                if error_code != pybonjour.kDNSServiceErr_NoError:
                        self.bus.log("Error in DNS-SD registration: {0}".format(
                            pybonjour.BonjourError(error_code)))

                self.reg_ok = True
                self.name = name
                if self.name != self.wanted_name:
                        self.bus.log("DNS-SD service name changed to: {0}".format(
                            self.name))

        def start(self):
                self.bus.log("Starting DNS-SD registration.")

                txt_r = pybonjour.TXTRecord()
                txt_r["url"] = self.url
                txt_r["type"] = "mirror"

                to_val = 10
                timedout = False

                try:
                        self.sd_hdl = pybonjour.DNSServiceRegister(
                            name=self.name, regtype=self.regtype,
                            port=self.port, txtRecord=txt_r,
                            callBack=self.reg_cb)
                except pybonjour.BonjourError as e:
                        self.bus.log("DNS-SD service registration failed: {0}".format(
                            e))
                        return

                try:
                        while not timedout:
                                avail = select.select([self.sd_hdl], [], [],
                                    to_val)
                                if self.sd_hdl in avail[0]:
                                        pybonjour.DNSServiceProcessResult(
                                            self.sd_hdl)
                                        to_val = 0
                                else:
                                        timedout = True
                except pybonjour.BonjourError as e:
                        self.bus.log("DNS-SD service registration failed: {0}".format(
                            e))

                if not self.reg_ok:
                        self.bus.log("DNS-SD registration timed out.")
                        return
                self.bus.log("Finished DNS-SD registration.")

        def exit(self):
                self.bus.log("DNS-SD plugin exited")
                if self.sd_hdl:
                        self.sd_hdl.close()
                self.sd_hdl = None
                self.bus.log("Service unregistration for DNS-SD complete.")


class BackgroundTaskPlugin(SimplePlugin):
        """This class allows background task execution for the depot server.  It
        is designed in such a way as to only allow a few tasks to be queued
        for execution at a time.
        """

        def __init__(self, bus):
                # Setup the background task queue.
                SimplePlugin.__init__(self, bus)
                self.__q = queue.Queue(10)
                self.__thread = None

        def put(self, task, *args, **kwargs):
                """Schedule the given task for background execution if queue
                isn't full.
                """
                if self.__q.unfinished_tasks > 9:
                        raise queue.Full()
                self.__q.put_nowait((task, args, kwargs))

        def run(self):
                """Run any background task scheduled for execution."""
                while self.__running:
                        try:
                                try:
                                        # A brief timeout here is necessary
                                        # to reduce CPU usage and to ensure
                                        # that shutdown doesn't wait forever
                                        # for a new task to appear.
                                        task, args, kwargs = \
                                            self.__q.get(timeout=.5)
                                except queue.Empty:
                                        continue
                                task(*args, **kwargs)
                                if hasattr(self.__q, "task_done"):
                                        # Task is done; mark it so.
                                        self.__q.task_done()
                        except:
                                self.bus.log("Failure encountered executing "
                                    "background task {0!r}.".format(self),
                                    traceback=True)

        def start(self):
                """Start the background task plugin."""
                self.__running = True
                if not self.__thread:
                        # Create and start a thread for the caller.
                        self.__thread = threading.Thread(target=self.run)
                        self.__thread.start()
        # Priority must be higher than the Daemonizer plugin to avoid threads
        # starting before fork().  Daemonizer has a priority of 65, as noted
        # at this URI: http://www.cherrypy.org/wiki/BuiltinPlugins
        start.priority = 66

        def stop(self):
                """Stop the background task plugin."""
                self.__running = False
                if self.__thread:
                        # Wait for the thread to terminate.
                        self.__thread.join()
                        self.__thread = None


class DepotConfig(object):
        """Returns an object representing a configuration interface for a
        a pkg(5) depot server.

        The class of the object returned will depend upon the specified
        configuration target (which is used as to retrieve and store
        configuration data).

        'target' is the optional location to retrieve existing configuration
        data or store the configuration data when requested.  The location
        can be None, the pathname of a file, or an SMF FMRI.  If a pathname is
        provided, and does not exist, it will be created if needed.

        'overrides' is a dictionary of property values indexed by section name
        and property name.  If provided, it will override any values read from
        an existing file or any defaults initially assigned.

        'version' is an integer value specifying the set of configuration data
        to use for the operation.  If not provided, the version will be based
        on the target if supported.  If a version cannot be determined, the
        newest version will be assumed.
        """

        # This dictionary defines the set of default properties and property
        # groups for a depot configuration indexed by version.
        __defs = {
            4: [
                cfg.PropertySection("pkg", [
                    cfg.PropList("address"),
                    cfg.PropDefined("cfg_file", allowed=["", "<pathname>"]),
                    cfg.Property("content_root"),
                    cfg.PropList("debug", allowed=["", "headers",
                        "hash=sha256", "hash=sha1+sha256", "hash=sha512_256",
                        "hash=sha1+sha512_256"]),
                    cfg.PropList("disable_ops"),
                    cfg.PropDefined("image_root", allowed=["",
                        "<abspathname>"]),
                    cfg.PropDefined("inst_root", allowed=["", "<pathname>"]),
                    cfg.PropBool("ll_mirror"),
                    cfg.PropDefined("log_access", allowed=["", "stderr",
                        "stdout", "none", "<pathname>"]),
                    cfg.PropDefined("log_errors", allowed=["", "stderr",
                        "stdout", "none", "<pathname>"], default="stderr"),
                    cfg.PropBool("mirror"),
                    cfg.PropDefined("pkg_root", allowed=["/", "<abspathname>"],
                        default="/"),
                    cfg.PropInt("port"),
                    cfg.PropPubURI("proxy_base"),
                    cfg.PropBool("readonly"),
                    cfg.PropInt("socket_timeout"),
                    cfg.PropInt("sort_file_max_size",
                        default=indexer.SORT_FILE_MAX_SIZE,
                        value_map={ "": indexer.SORT_FILE_MAX_SIZE }),
                    cfg.PropDefined("ssl_cert_file",
                        allowed=["", "<pathname>", "none"]),
                    cfg.PropDefined("ssl_dialog", allowed=["<exec:pathname>",
                        "builtin", "smf", "<smf:fmri>"], default="builtin"),
                    cfg.PropDefined("ssl_key_file",
                        allowed=["", "<pathname>", "none"]),
                    cfg.PropInt("threads"),
                    cfg.PropDefined("writable_root",
                        allowed=["", "<pathname>"]),
                ]),
                cfg.PropertySection("pkg_bui", [
                    cfg.PropDefined("feed_description"),
                    cfg.PropDefined("feed_icon",
                        default="web/_themes/pkg-block-icon.png"),
                    cfg.PropDefined("feed_logo",
                        default="web/_themes/pkg-block-logo.png"),
                    cfg.PropDefined("feed_name",
                        default="package repository feed"),
                    cfg.PropInt("feed_window", default=24)
                ]),
                cfg.PropertySection("pkg_secure", [
                    cfg.PropDefined("ssl_key_passphrase"),
                ]),
                cfg.PropertySection("nasty", [
                    cfg.PropInt("nasty_level"),
                    cfg.PropInt("nasty_sleep", default=35)
                ]),
            ],
        }

        def __new__(cls, target=None, overrides=misc.EmptyDict, version=None):
                if not target:
                        return cfg.Config(definitions=cls.__defs,
                            overrides=overrides, version=version)
                elif target.startswith("svc:"):
                        return cfg.SMFConfig(target, definitions=cls.__defs,
                            overrides=overrides, version=version)
                return cfg.FileConfig(target, definitions=cls.__defs,
                    overrides=overrides, version=version)
