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
# Copyright (c) 2008, 2010, Oracle and/or its affiliates. All rights reserved.
#

import cherrypy
from cherrypy.lib.static import serve_file
from email.utils import formatdate
from cherrypy.process.plugins import SimplePlugin

try:
        import pybonjour
except (OSError, ImportError):
        pass
else:
        import select

import cStringIO
import errno
import httplib
import inspect
import itertools
import os
import random
import re
import socket
import tarfile
import time
import urlparse
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
import pkg.client.publisher as publisher
import pkg.config as cfg
import pkg.fmri as fmri
import pkg.indexer as indexer
import pkg.manifest as manifest
import pkg.misc as misc
import pkg.p5i as p5i
import pkg.server.face as face
import pkg.server.repository as repo
import pkg.version as version

from pkg.server.query_parser import Query, ParseError, BooleanQueryException


class Dummy(object):
        """Dummy object used for dispatch method mapping."""
        pass

class _Depot(object):
        """Private, abstract, base class for all Depot classes."""

        nasty = 0

        def set_nasty(self, level):
                """Set the nasty level using an integer."""

                self.nasty = level

        def is_nasty(self):
                """Returns true if nasty has been enabled."""

                if self.nasty > 0:
                        return True
                return False

        def need_nasty(self):
                """Randomly returns true when the server should misbehave."""

                if random.randint(1, 100) <= self.nasty:
                        return True
                return False

        def need_nasty_bonus(self, bonus=0):
                """Used to temporarily apply extra nastiness to an operation."""

                if self.nasty + bonus > 95:
                        nasty = 95
                else:
                        nasty = self.nasty + bonus

                if random.randint(1, 100) <= nasty:
                        return True
                return False

        def need_nasty_occasionally(self):
                if random.randint(1, 500) <= self.nasty:
                        return True
                return False

        def need_nasty_infrequently(self):
                if random.randint(1, 2000) <= self.nasty:
                        return True
                return False

        def need_nasty_rarely(self):
                if random.randint(1, 20000) <= self.nasty:
                        return True
                return False


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
            "filelist",
            "file",
            "open",
            "close",
            "abandon",
            "add",
            "p5i",
            "publisher",
            "index"
        ]

        REPO_OPS_READONLY = [
            "versions",
            "search",
            "catalog",
            "info",
            "manifest",
            "filelist",
            "file",
            "p5i",
            "publisher"
        ]

        REPO_OPS_MIRROR = [
            "versions",
            "filelist",
            "file",
            "publisher"
        ]

        content_root = None
        web_root = None

        def __init__(self, repo, dconf):
                """Initialize and map the valid operations for the depot.  While
                doing so, ensure that the operations have been explicitly
                "exposed" for external usage."""

                self.cfg = dconf
                self.repo = repo

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

                # Handles the BUI (Browser User Interface).
                face.init(self)

                # Store any possible configuration changes.
                repo.write_config()

                if repo.mirror or not repo.repo_root:
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

                if hasattr(cherrypy.engine, "signal_handler"):
                        # This handles SIGUSR1
                        cherrypy.engine.subscribe("graceful", self.refresh)

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

                rs = self.repo.cfg.get_property("repository",
                    "refresh_seconds")
                if max_age is None:
                        max_age = min((rs, expires))

                now = cherrypy.response.time
                if op_name == "publisher" or op_name == "search" or \
                    op_name == "catalog":
                        # For these operations, cap the value based on
                        # refresh_seconds.
                        expires = now + min((rs, max_age))
                else:
                        expires = now + expires

                headers = cherrypy.response.headers
                headers["Cache-Control"] = \
                    "must-revalidate, no-transform, max-age=%d" % max_age
                headers["Expires"] = formatdate(timeval=expires, usegmt=True)

        def refresh(self):
                """Catch SIGUSR1 and reload the depot information."""
                self.repo.reload()
                if type(self.cfg) == cfg.SMFConfig:
                        # For all other cases, reloading depot configuration
                        # isn't desirable (because of command-line overrides).
                        self.cfg.reset()

                # Handles the BUI (Browser User Interface).
                face.init(self)

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
                        return face.respond(self, request, response)

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

        @cherrypy.tools.response_headers(headers=\
            [("Content-Type", "text/plain; charset=utf-8")])
        def versions_0(self, *tokens):
                """Output a text/plain list of valid operations, and their
                versions, supported by the repository."""

                self.__set_response_expires("versions", 5*60, 5*60)
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
                response.headers["Content-type"] = "text/plain; charset=utf-8"
                self.__set_response_expires("search", 86400, 86400)

                try:
                        token = tokens[0]
                except IndexError:
                        token = None

                query_args_lst = [str(Query(token, case_sensitive=False,
                    return_type=Query.RETURN_ACTIONS, num_to_return=None,
                    start_point=None))]

                try:
                        res_list = self.repo.search(query_args_lst)
                except repo.RepositorySearchUnavailableError, e:
                        raise cherrypy.HTTPError(httplib.SERVICE_UNAVAILABLE,
                            str(e))
                except repo.RepositoryError, e:
                        # Treat any remaining repository error as a 404, but
                        # log the error and include the real failure
                        # information.
                        cherrypy.log("Request failed: %s" % str(e))
                        raise cherrypy.HTTPError(httplib.NOT_FOUND, str(e))

                # Translate the results from v1 format into what a v0
                # searcher expects as results.
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

                # Check for the GET method of doing a search request.
                try:
                        query_str_lst = [args[0]]
                except IndexError:
                        pass

                # Check for the POST method of doing a search request.
                if not query_str_lst:
                        query_str_lst = params.values()
                elif params.values():
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST,
                            "args:%s, params:%s" % (args, params))

                if not query_str_lst:
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST)

                if not self.repo.search_available:
                        raise cherrypy.HTTPError(httplib.SERVICE_UNAVAILABLE,
                            "Search temporarily unavailable")

                try:
                        res_list = self.repo.search(query_str_lst)
                except (ParseError, BooleanQueryException), e:
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST, str(e))
                except repo.RepositorySearchUnavailableError, e:
                        raise cherrypy.HTTPError(httplib.SERVICE_UNAVAILABLE,
                            str(e))
                except repo.RepositoryError, e:
                        # Treat any remaining repository error as a 404, but
                        # log the error and include the real failure
                        # information.
                        cherrypy.log("Request failed: %s" % str(e))
                        raise cherrypy.HTTPError(httplib.NOT_FOUND, str(e))

                response = cherrypy.response
                response.headers["Content-type"] = "text/plain; charset=utf-8"
                self.__set_response_expires("search", 86400, 86400)

                # In order to be able to have a return code distinguish between
                # no results and search unavailable, we need to use a different
                # http code.  Check and see if there's at least one item in
                # the results.  If not, set the result code to be NO_CONTENT
                # and return.  If there is at least one result, put the result
                # examined back at the front of the results and stream them
                # to the user.
                if len(res_list) == 1:
                        try:
                                tmp = res_list[0].next()
                                res_list = [itertools.chain([tmp], res_list[0])]
                        except StopIteration:
                                cherrypy.response.status = httplib.NO_CONTENT
                                return

                def output():
                        # Yield the string used to let the client know it's
                        # talking to a valid search server.
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
                """Provide a full version of the catalog, as appropriate, to
                the requesting client.  Incremental catalogs are not supported
                for v0 catalog clients."""

                request = cherrypy.request

                # Response headers have to be setup *outside* of the function
                # that yields the catalog content.
                c = self.repo.catalog
                response = cherrypy.response
                response.headers["Content-type"] = "text/plain; charset=utf-8"
                response.headers["Last-Modified"] = c.last_modified.isoformat()
                response.headers["X-Catalog-Type"] = "full"
                self.__set_response_expires("catalog", 86400, 86400)

                def output():
                        try:
                                for l in self.repo.catalog_0():
                                        yield l
                        except repo.RepositoryError, e:
                                # Can't do anything in a streaming generator
                                # except log the error and return.
                                cherrypy.log("Request failed: %s" % str(e))
                                return

                return output()

        catalog_0._cp_config = { "response.stream": True }

        def catalog_1(self, *tokens):
                """Outputs the contents of the specified catalog file, using the
                name in the request path, directly to the client."""

                try:
                        name = tokens[0]
                except IndexError:
                        raise cherrypy.HTTPError(httplib.FORBIDDEN,
                            _("Directory listing not allowed."))

                try:
                        fpath = self.repo.catalog_1(name)
                except repo.RepositoryError, e:
                        # Treat any remaining repository error as a 404, but
                        # log the error and include the real failure
                        # information.
                        cherrypy.log("Request failed: %s" % str(e))
                        raise cherrypy.HTTPError(httplib.NOT_FOUND, str(e))

                self.__set_response_expires("catalog", 86400, 86400)
                return serve_file(fpath, "text/plain; charset=utf-8")

        catalog_1._cp_config = { "response.stream": True }

        def manifest_0(self, *tokens):
                """The request is an encoded pkg FMRI.  If the version is
                specified incompletely, we return an error, as the client is
                expected to form correct requests based on its interpretation
                of the catalog and its image policies."""

                try:
                        cat = self.repo.catalog
                        pubs = cat.publishers()
                except Exception, e:
                        cherrypy.log("Request Failed: %s" % e)
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST, str(e))

                # A broken proxy (or client) has caused a fully-qualified FMRI
                # to be split up.
                comps = [t for t in tokens]
                if not comps:
                        raise cherrypy.HTTPError(httplib.FORBIDDEN,
                            _("Directory listing not allowed."))

                if comps[0] == "pkg:" and comps[1] in pubs:
                        # Only one slash here as another will be added below.
                        comps[0] += "/"

                # Parse request into FMRI component and decode.
                try:
                        # If more than one token (request path component) was
                        # specified, assume that the extra components are part
                        # of the fmri and have been split out because of bad
                        # proxy behaviour.
                        pfmri = "/".join(comps)
                        fpath = self.repo.manifest(pfmri)
                except (IndexError, repo.RepositoryInvalidFMRIError), e:
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST, str(e))
                except repo.RepositoryError, e:
                        # Treat any remaining repository error as a 404, but
                        # log the error and include the real failure
                        # information.
                        cherrypy.log("Request failed: %s" % str(e))
                        raise cherrypy.HTTPError(httplib.NOT_FOUND, str(e))

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

        def filelist_0(self, *tokens, **params):
                """Request data contains application/x-www-form-urlencoded
                entries with the requested filenames.  The resulting tar stream
                is output directly to the client. """

                try:
                        self.repo.inc_flist()

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
                                filepath = self.repo.cache_store.lookup(v)

                                # If file isn't here, skip it
                                if not filepath:
                                        continue

                                tar_stream.add(filepath, v, False)
                                self.repo.inc_flist_files()

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
            "tools.response_headers.headers": [
                ("Content-Type", "application/data"),
                ("Pragma", "no-cache"),
                ("Cache-Control", "no-cache, no-transform, must-revalidate"),
                ("Expires", 0)
            ]
        }

        def file_0(self, *tokens):
                """Outputs the contents of the file, named by the SHA-1 hash
                name in the request path, directly to the client."""

                try:
                        fhash = tokens[0]
                except IndexError:
                        fhash = None

                try:
                        fpath = self.repo.file(fhash)
                except repo.RepositoryFileNotFoundError, e:
                        raise cherrypy.HTTPError(httplib.NOT_FOUND, str(e))
                except repo.RepositoryError, e:
                        # Treat any remaining repository error as a 404, but
                        # log the error and include the real failure
                        # information.
                        cherrypy.log("Request failed: %s" % str(e))
                        raise cherrypy.HTTPError(httplib.NOT_FOUND, str(e))

                self.__set_response_expires("file", 86400*365, 86400*365)
                return serve_file(fpath, "application/data")

        file_0._cp_config = { "response.stream": True }

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

                try:
                        trans_id = self.repo.open(client_release, pfmri)
                        response.headers["Content-type"] = "text/plain; charset=utf-8"
                        response.headers["Transaction-ID"] = trans_id
                except repo.RepositoryError, e:
                        # Assume a bad request was made.  A 404 can't be
                        # returned here as misc.versioned_urlopen will interpret
                        # that to mean that the server doesn't support this
                        # operation.
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST, str(e))

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
                        # Assume "True" for backwards compatibility.
                        add_to_catalog = int(request.headers.get(
                            "X-IPkg-Add-To-Catalog", 1))

                        # Force a boolean value.
                        if add_to_catalog:
                                add_to_catalog = True
                        else:
                                add_to_catalog = False
                except ValueError, e:
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST,
                            "X-IPkg-Add-To-Catalog" % e)

                try:
                        pfmri, pstate = self.repo.close(trans_id,
                            refresh_index=refresh_index,
                            add_to_catalog=add_to_catalog)
                except repo.RepositoryError, e:
                        # Assume a bad request was made.  A 404 can't be
                        # returned here as misc.versioned_urlopen will interpret
                        # that to mean that the server doesn't support this
                        # operation.
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST, str(e))

                response = cherrypy.response
                response.headers["Package-FMRI"] = pfmri
                response.headers["State"] = pstate

        @cherrypy.tools.response_headers(headers=[("Pragma", "no-cache"),
            ("Cache-Control", "no-cache, no-transform, must-revalidate"),
            ("Expires", 0)])
        def abandon_0(self, *tokens):
                """Aborts an in-flight transaction for the Transaction ID
                specified in the request path.  Returns no output."""

                try:
                        # cherrypy decoded it, but we actually need it encoded.
                        trans_id = urllib.quote(tokens[0], "")
                except IndexError:
                        trans_id = None

                try:
                        self.repo.abandon(trans_id)
                except repo.RepositoryError, e:
                        # Assume a bad request was made.  A 404 can't be
                        # returned here as misc.versioned_urlopen will interpret
                        # that to mean that the server doesn't support this
                        # operation.
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST, str(e))

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

                try:
                        action = actions.types[entry_type](data, **attrs)
                except actions.ActionError, e:
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST, str(e))

                # XXX Once actions are labelled with critical nature.
                # if entry_type in critical_actions:
                #         self.critical = True

                try:
                        self.repo.add(trans_id, action)
                except repo.RepositoryError, e:
                        # Assume a bad request was made.  A 404 can't be
                        # returned here as misc.versioned_urlopen will interpret
                        # that to mean that the server doesn't support this
                        # operation.
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST, str(e))

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

        @cherrypy.tools.response_headers(headers=[("Pragma", "no-cache"),
            ("Cache-Control", "no-cache, no-transform, must-revalidate"),
            ("Expires", 0)])
        def index_0(self, *tokens):
                """Triggers a refresh of the search indices.
                Returns no output."""

                cmd = tokens[0]

                if cmd == "refresh":
                        try:
                                self.repo.refresh_index()
                        except repo.RepositoryError, e:
                                # Assume a bad request was made.  A 404 can't be
                                # returned here as misc.versioned_urlopen will interpret
                                # that to mean that the server doesn't support this
                                # operation.
                                raise cherrypy.HTTPError(httplib.BAD_REQUEST, str(e))
                else:
                        cherrypy.log("Unknown index subcommand: %s" % cmd)
                        raise cherrypy.HTTPError(httplib.NOT_FOUND, str(e))

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
                        cat = self.repo.catalog
                        pubs = cat.publishers()
                except Exception, e:
                        cherrypy.log("Request Failed: %s" % e)
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST, str(e))

                # A broken proxy (or client) has caused a fully-qualified FMRI
                # to be split up.
                comps = [t for t in tokens]
                if comps[0] == "pkg:" and comps[1] in pubs:
                        # Only one slash here as another will be added below.
                        comps[0] += "/"

                # Parse request into FMRI component and decode.
                try:
                        # If more than one token (request path component) was
                        # specified, assume that the extra components are part
                        # of the fmri and have been split out because of bad
                        # proxy behaviour.
                        pfmri = "/".join(comps)
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
                        mpath = os.path.join(self.repo.manifest_root,
                            f.get_dir_path())
                except fmri.FmriError, e:
                        # If the FMRI operation couldn't be performed, assume
                        # the client made a bad request.
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST, str(e))

                if not os.path.exists(mpath):
                        raise cherrypy.HTTPError(httplib.NOT_FOUND)

                m.set_content(file(mpath).read())

                publisher, name, ver = f.tuple()
                if not publisher:
                        publisher = self.repo.cfg.get_property("publisher",
                            "prefix")
                        if not publisher:
                                publisher = ""

                summary = m.get("pkg.summary", m.get("description", ""))

                lsummary = cStringIO.StringIO()
                for i, entry in enumerate(m.gen_actions_by_type("license")):
                        if i > 0:
                                lsummary.write("\n")
                        lpath = self.repo.cache_store.lookup(entry.hash)

                        lfile = file(lpath, "rb")
                        misc.gunzip_from_stream(lfile, lsummary)
                lsummary.seek(0)

                self.__set_response_expires("info", 86400*365, 86400*365)
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
    ver.branch, ver.get_timestamp().strftime("%c"),
    misc.bytes_to_str(m.get_size()), f, lsummary.read())

        def __get_publisher(self):
                rargs = {}
                for prop in ("collection_type", "description", "legal_uris",
                    "mirrors", "name", "origins", "refresh_seconds",
                    "registration_uri", "related_uris"):
                        rargs[prop] = self.repo.cfg.get_property(
                            "repository", prop)

                repo = publisher.Repository(**rargs)
                alias = self.repo.cfg.get_property("publisher", "alias")
                pfx = self.repo.cfg.get_property("publisher", "prefix")
                return publisher.Publisher(pfx, alias=alias,
                    repositories=[repo])

        @cherrypy.tools.response_headers(headers=[(
            "Content-Type", p5i.MIME_TYPE)])
        def publisher_0(self, *tokens):
                """Returns a pkg(5) information datastream based on the
                repository configuration's publisher information."""

                try:
                        pub = self.__get_publisher()
                except Exception, e:
                        # If the Publisher object creation fails, return a not
                        # found error to the client so it will treat it as an
                        # an unsupported operation.
                        cherrypy.log("Request failed: %s" % str(e))
                        raise cherrypy.HTTPError(httplib.NOT_FOUND, str(e))

                buf = cStringIO.StringIO()
                try:
                        p5i.write(buf, [pub])
                except Exception, e:
                        # Treat any remaining error as a 404, but log it and
                        # include the real failure information.
                        cherrypy.log("Request failed: %s" % str(e))
                        raise cherrypy.HTTPError(httplib.NOT_FOUND, str(e))
                buf.seek(0)
                self.__set_response_expires("publisher", 86400*365, 86400*365)
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
                        cat = self.repo.catalog
                        pubs = cat.publishers()
                except Exception, e:
                        cherrypy.log("Request Failed: %s" % e)
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST, str(e))

                # A broken proxy (or client) has caused a fully-qualified FMRI
                # to be split up.
                comps = [t for t in tokens]
                if comps[0] == "pkg:" and comps[1] in pubs:
                        # Only one slash here as another will be added below.
                        comps[0] += "/"

                try:
                        # If more than one token (request path component) was
                        # specified, assume that the extra components are part
                        # of an FMRI and have been split out because of bad
                        # proxy behaviour.
                        pfmri = "/".join(comps)
                except IndexError:
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST)

                # XXX This is a hack to deal with the fact that packagemanager
                # brokenly expects all p5i URIs or files to have a .p5i
                # extension instead of just relying on the api to parse it.
                # This hack allows callers to append a .p5i extension to the
                # URI without affecting the operation.
                if pfmri.endswith(".p5i"):
                        end = len(pfmri) - len(".p5i")
                        pfmri = pfmri[:end]

                matcher = None
                if "*" not in pfmri and "@" not in pfmri:
                        matcher = fmri.exact_name_match
                elif "*" in pfmri:
                        matcher = fmri.glob_match
                        try:
                                # XXX 5.11 needs to be saner
                                pfmri = fmri.MatchingPkgFmri(pfmri, "5.11")
                        except Exception, e:
                                raise cherrypy.HTTPError(httplib.BAD_REQUEST,
                                    str(e))

                # Attempt to find matching entries in the catalog.
                try:
                        matches, unmatched = catalog.extract_matching_fmris(cat.fmris(),
                            patterns=[pfmri], constraint=version.CONSTRAINT_AUTO,
                            matcher=matcher)
                except Exception, e:
                        cherrypy.log("Request Failed: %s" % e)
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST, str(e))

                if not matches:
                        raise cherrypy.HTTPError(httplib.NOT_FOUND, _("No "
                            "matching FMRI found in repository catalog."))
                elif matcher in (fmri.exact_name_match, fmri.glob_match):
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

                try:
                        pub = self.__get_publisher()
                except Exception, e:
                        # If the Publisher object creation fails, return a not
                        # found error to the client so it will treat it as an
                        # unsupported operation.
                        cherrypy.log("Request failed: %s" % str(e))
                        raise cherrypy.HTTPError(httplib.NOT_FOUND,
                            str(e))

                buf = cStringIO.StringIO()
                try:
                        pkg_names = { pub.prefix: matches }
                        p5i.write(buf, [pub], pkg_names=pkg_names)
                except Exception, e:
                        # Treat any remaining error as a 404, but log it and
                        # include the real failure information.
                        cherrypy.log("Request failed: %s" % str(e))
                        raise cherrypy.HTTPError(httplib.NOT_FOUND, str(e))
                buf.seek(0)
                self.__set_response_expires("p5i", 86400*365, 86400*365)
                return buf.getvalue()


class NastyDepotHTTP(DepotHTTP):
        """A class that creates a depot that misbehaves.  Naughty
        depots are useful for testing."""

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

                cherrypy.tools.nasty_httperror = cherrypy.Tool('before_handler',
                    NastyDepotHTTP.nasty_retryable_error)

        # Method for CherryPy tool for Nasty Depot
        @staticmethod
        def nasty_retryable_error(bonus=0):
                """A static method that's used by the cherrpy tools,
                and in depot code, to generate a retryable HTTP error."""

                retryable_errors = [httplib.REQUEST_TIMEOUT,
                    httplib.BAD_GATEWAY, httplib.GATEWAY_TIMEOUT]

                # NASTY
                # emit error code that client should know how to retry
                if self.need_nasty_bonus(bonus):
                        code = retryable_errors[random.randint(0,
                            len(retryable_errors) - 1)]
                        raise cherrypy.HTTPError(code)

        # Override _cp_config for catalog_0 operation
        def catalog_0(self, *tokens):
                """Provide a full version of the catalog, as appropriate, to
                the requesting client.  Incremental catalogs are not supported
                for v0 catalog clients."""

                request = cherrypy.request

                # Response headers have to be setup *outside* of the function
                # that yields the catalog content.
                c = self.repo.catalog
                response = cherrypy.response
                response.headers["Content-type"] = "text/plain; charset=utf-8"
                response.headers["Last-Modified"] = c.last_modified.isoformat()
                response.headers["X-Catalog-Type"] = "full"

                def output():
                        try:
                                for l in self.repo.catalog_0():
                                        yield l
                        except repo.RepositoryError, e:
                                # Can't do anything in a streaming generator
                                # except log the error and return.
                                cherrypy.log("Request failed: %s" % str(e))
                                return

                return output()

        catalog_0._cp_config = {
            "response.stream": True,
            "tools.nasty_httperror.on": True,
            "tools.nasty_httperror.bonus": 1
        }

        def manifest_0(self, *tokens):
                """The request is an encoded pkg FMRI.  If the version is
                specified incompletely, we return an error, as the client is
                expected to form correct requests based on its interpretation
                of the catalog and its image policies."""

                try:
                        cat = self.repo.catalog
                        pubs = cat.publishers()
                except Exception, e:
                        cherrypy.log("Request Failed: %s" % e)
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST, str(e))

                # A broken proxy (or client) has caused a fully-qualified FMRI
                # to be split up.
                comps = [t for t in tokens]
                if comps[0] == "pkg:" and comps[1] in pubs:
                        # Only one slash here as another will be added below.
                        comps[0] += "/"

                # Parse request into FMRI component and decode.
                try:
                        # If more than one token (request path component) was
                        # specified, assume that the extra components are part
                        # of the fmri and have been split out because of bad
                        # proxy behaviour.
                        pfmri = "/".join(comps)
                        fpath = self.repo.manifest(pfmri)
                except (IndexError, repo.RepositoryInvalidFMRIError), e:
                        raise cherrypy.HTTPError(httplib.BAD_REQUEST, str(e))
                except repo.RepositoryError, e:
                        # Treat any remaining repository error as a 404, but
                        # log the error and include the real failure
                        # information.
                        cherrypy.log("Request failed: %s" % str(e))
                        raise cherrypy.HTTPError(httplib.NOT_FOUND, str(e))

                # NASTY
                # Stash manifest entry for later use.
                # Toss out the list if it's larger than 1024 items.
                if len(self.requested_manifests) > 1024:
                        self.requested_manifests = [fpath]
                else:
                        self.requested_manifests.append(fpath)

                # NASTY
                # Send an error before serving the manifest, perhaps
                if self.need_nasty():
                        self.nasty_retryable_error()
                elif self.need_nasty_infrequently():
                        # Fall asleep before finishing the request
                        time.sleep(35)
                elif self.need_nasty_rarely():
                        # Forget that the manifest is here
                        raise cherrypy.HTTPError(httplib.NOT_FOUND)

                # NASTY
                # Send the wrong manifest
                if self.need_nasty_rarely():
                        pick = random.randint(0,
                            len(self.requested_manifests) - 1)
                        badpath = self.requested_manifests[pick]

                        return serve_file(badpath, "text/plain; charset=utf-8")

                # NASTY
                # Call a misbehaving serve_file
                return self.nasty_serve_file(fpath, "text/plain; charset=utf-8")

        manifest_0._cp_config = { "response.stream": True }

        def filelist_0(self, *tokens, **params):
                """Request data contains application/x-www-form-urlencoded
                entries with the requested filenames.  The resulting tar stream
                is output directly to the client. """

                try:
                        self.repo.inc_flist()

                        # NASTY
                        if self.need_nasty_occasionally():
                                return

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

                        # NASTY
                        if self.need_nasty_infrequently():
                                time.sleep(35)

                        for v in params.values():

                                # NASTY
                                # Stash filename for later use.
                                # Toss out the list if it's larger than 1024
                                # items.
                                if len(self.requested_files) > 1024:
                                        self.requested_files = [v]
                                else:
                                        self.requested_files.append(v)

                                # NASTY
                                if self.need_nasty_infrequently():
                                        # Give up early
                                        break
                                elif self.need_nasty_infrequently():
                                        # Skip this file
                                        continue
                                elif self.need_nasty_rarely():
                                        # Take a nap
                                        time.sleep(35)

                                filepath = self.repo.cache_store.lookup(v)

                                # If file isn't here, skip it
                                if not os.path.exists(filepath):
                                        continue

                                # NASTY
                                # Send a file with the wrong content
                                if self.need_nasty_rarely():
                                        pick = random.randint(0,
                                            len(self.requested_files) - 1)
                                        badfn = self.requested_files[pick]
                                        badpath = self.__get_bad_path(badfn)

                                        tar_stream.add(badpath, v, False)
                                else:
                                        tar_stream.add(filepath, v, False)

                                self.repo.inc_flist_files()

                        # NASTY
                        # Write garbage into the stream
                        if self.need_nasty_infrequently():
                                f.write("NASTY!")

                        # NASTY
                        # Send an extraneous file
                        if self.need_nasty_infrequently():
                                pick = random.randint(0,
                                    len(self.requested_files) - 1)
                                extrafn = self.requested_files[pick]
                                extrapath = self.repo.cache_store.lookup(
                                    extrafn)

                                tar_stream.add(extrapath, extrafn, False)

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
            "tools.nasty_httperror.on": True,
            "tools.response_headers.on": True,
            "tools.response_headers.headers": [
                ("Content-Type", "application/data"),
                ("Pragma", "no-cache"),
                ("Cache-Control", "no-cache, must-revalidate"),
                ("Expires", 0)
            ]
        }

        def __get_bad_path(self, v):
                return os.path.join(self.repo.cache_store.root,
                    self.repo.cache_store.layouts[0].lookup(v))

        def file_0(self, *tokens):
                """Outputs the contents of the file, named by the SHA-1 hash
                name in the request path, directly to the client."""

                try:
                        fhash = tokens[0]
                except IndexError:
                        fhash = None

                try:
                        fpath = self.repo.file(fhash)
                except repo.RepositoryFileNotFoundError, e:
                        raise cherrypy.HTTPError(httplib.NOT_FOUND, str(e))
                except repo.RepositoryError, e:
                        # Treat any remaining repository error as a 404, but
                        # log the error and include the real failure
                        # information.
                        cherrypy.log("Request failed: %s" % str(e))
                        raise cherrypy.HTTPError(httplib.NOT_FOUND, str(e))

                # NASTY
                # Stash filename for later use.
                # Toss out the list if it's larger than 1024 items.
                if len(self.requested_files) > 1024:
                        self.requested_files = [fhash]
                else:
                        self.requested_files.append(fhash)

                # NASTY
                # Send an error before serving the file, perhaps
                if self.need_nasty():
                        self.nasty_retryable_error()
                elif self.need_nasty_rarely():
                        # Fall asleep before finishing the request
                        time.sleep(35)
                elif self.need_nasty_rarely():
                        # Forget that the file is here
                        raise cherrypy.HTTPError(httplib.NOT_FOUND)

                # NASTY
                # Send the wrong file
                if self.need_nasty_rarely():
                        pick = random.randint(0, len(self.requested_files) - 1)
                        badfn = self.requested_files[pick]
                        badpath = self.__get_bad_path(badfn)

                        return serve_file(badpath, "application/data")

                # NASTY
                # Call a misbehaving serve_file
                return self.nasty_serve_file(fpath, "application/data")

        file_0._cp_config = { "response.stream": True }

        def catalog_1(self, *tokens):
                """Outputs the contents of the specified catalog file, using the
                name in the request path, directly to the client."""

                try:
                        name = tokens[0]
                except IndexError:
                        raise cherrypy.HTTPError(httplib.FORBIDDEN,
                            _("Directory listing not allowed."))

                try:
                        fpath = self.repo.catalog_1(name)
                except repo.RepositoryError, e:
                        # Treat any remaining repository error as a 404, but
                        # log the error and include the real failure
                        # information.
                        cherrypy.log("Request failed: %s" % str(e))
                        raise cherrypy.HTTPError(httplib.NOT_FOUND, str(e))

                # NASTY
                # Stash catalog entry for later use.
                # Toss out the list if it's larger than 1024 items.
                if len(self.requested_catalogs) > 1024:
                        self.requested_catalogs = [fpath]
                else:
                        self.requested_catalogs.append(fpath)

                # NASTY
                # Send an error before serving the catalog, perhaps
                if self.need_nasty():
                        self.nasty_retryable_error()
                elif self.need_nasty_rarely():
                        # Fall asleep before finishing the request
                        time.sleep(35)
                elif self.need_nasty_rarely():
                        # Forget that the catalog is here
                        raise cherrypy.HTTPError(httplib.NOT_FOUND)

                # NASTY
                # Send the wrong catalog
                if self.need_nasty_rarely():
                        pick = random.randint(0,
                            len(self.requested_catalogs) - 1)
                        badpath = self.requested_catalogs[pick]

                        return serve_file(badpath, "text/plain; charset=utf-8")

                # NASTY
                # Call a misbehaving serve_file
                return self.nasty_serve_file(fpath, "text/plain; charset=utf-8")

        catalog_1._cp_config = { "response.stream": True }


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
                        raise cherrypy.HTTPError(httplib.NOT_FOUND)

                # NASTY
                # Send incorrect content length
                if self.need_nasty_rarely():
                        response.headers["Content-Length"] = str(filesz +
                                random.randint(1, 1024))
                        already_nasty = True
                else:
                        response.headers["Content-Length"] = str(filesz)

                # NASTY
                # Send truncated file
                if self.need_nasty_rarely() and not already_nasty:
                        response.body = nfile.read(filesz - random.randint(1,
                            filesz - 1))
                        # If we're sending data, lie about the length and
                        # make the client catch us.
                        if content_type == "application/data":
                                response.headers["Content-Length"] = str(
                                    len(response.body))
                elif self.need_nasty_rarely() and not already_nasty:
                        # Write garbage into the response
                        response.body = nfile.read(filesz)
                        response.body += "NASTY!"
                        # If we're sending data, lie about the length and
                        # make the client catch us.
                        if content_type == "application/data":
                                response.headers["Content-Length"] = str(
                                    len(response.body))
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

                self.name = "pkg(5) mirror on %s" % socket.gethostname()
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

                netloc = "%s:%s" % (socket.getfqdn(), self.port)
                self.url = urlparse.urlunsplit((proto, netloc, '', '', ''))

        def reg_cb(self, sd_hdl, flags, error_code, name, regtype, domain):
                """Callback invoked by service register function.  Arguments
                are determined by the pybonjour framework, and must not
                be changed.
                """

                if error_code != pybonjour.kDNSServiceErr_NoError:
                        self.bus.log("Error in DNS-SD registration: %s" %
                            pybonjour.BonjourError(error_code))

                self.reg_ok = True
                self.name = name
                if self.name != self.wanted_name:
                        self.bus.log("DNS-SD service name changed to: %s" %
                            self.name)

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
                except pybonjour.BonjourError, e:
                        self.bus.log("DNS-SD service registration failed: %s" %
                            e)
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
                except pybonjour.BonjourError, e:
                        self.bus.log("DNS-SD service registration failed: %s" %
                            e)

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
                    cfg.PropDefined("cfg_file", allowed=["", "<pathname>"]),
                    cfg.Property("content_root"),
                    cfg.PropList("debug", allowed=["", "headers"]),
                    cfg.PropPublisher("default_publisher"),
                    cfg.PropList("disable_ops"),
                    cfg.PropDefined("file_root", allowed=["", "<pathname>"]),
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
                        default=indexer.SORT_FILE_MAX_SIZE),
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
