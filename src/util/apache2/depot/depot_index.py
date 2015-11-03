#!/usr/bin/python2.7
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
# Copyright (c) 2013, 2015, Oracle and/or its affiliates. All rights reserved.

from __future__ import print_function
import atexit
import cherrypy
import logging
import mako
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import traceback

from six.moves import http_client, queue
from six.moves.urllib.parse import quote
from six.moves.urllib.request import urlopen

import pkg.misc as misc
import pkg.p5i
import pkg.server.api
import pkg.server.repository as sr
import pkg.server.depot as sd
import pkg.server.face as face

# redirecting stdout for proper WSGI portability
sys.stdout = sys.stderr

# a global dictionary containing sr.Repository objects, keyed by
# repository prefix (not publisher prefix).
repositories = {}

# a global dictionary containing DepotBUI objects, keyed by repository
# prefix.
depot_buis = {}

# a global dictionary containing sd.DepotHTTP objects, keyed by repository
# prefix
depot_https = {}

# a lock used during server startup to ensure we don't try to index the same
# repository at once.
repository_lock = threading.Lock()

import gettext
gettext.install("/")

# How often we ping the depot while long-running background tasks are running.
# This should be set to less than the mod_wsgi inactivity-timeout (since
# pinging the depot causes activity, preventing mod_wsgi from shutting down the
# Python interpreter.)
KEEP_BUSY_INTERVAL = 120

class DepotException(Exception):
        """Super class for all exceptions raised by depot_index."""
        def __init__(self, request, message):
                self.request = request
                self.message = message
                self.http_status = http_client.INTERNAL_SERVER_ERROR

        def __str__(self):
                return "{0}: {1}".format(self.message, self.request)


class AdminOpsDisabledException(DepotException):
        """An exception thrown when this wsgi application hasn't been configured
        to allow admin/0 pkg(5) depot responses."""

        def __init__(self, request):
                self.request = request
                self.http_status = http_client.FORBIDDEN

        def __str__(self):
                return "admin/0 operations are disabled. " \
                    "See the config/allow_refresh SMF property. " \
                    "Request was: {0}".format(self.request)


class AdminOpNotSupportedException(DepotException):
        """An exception thrown when an admin request was made that isn't
        supported by the http-depot."""

        def __init__(self, request, cmd):
                self.request = request
                self.cmd = cmd
                self.http_status = http_client.NOT_IMPLEMENTED

        def __str__(self):
                return "admin/0 operations of type {type} are not " \
                    "supported by this repository. " \
                    "Request was: {request}".format(request=self.request,
                    type=self.cmd)


class IndexOpDisabledException(DepotException):
        """An exception thrown when we've been asked to refresh an index for
        a repository that doesn't have a writable_root property set."""

        def __init__(self, request):
                self.request = request
                self.http_status = http_client.FORBIDDEN

        def __str__(self):
                return "admin/0 operations to refresh indexes are not " \
                    "allowed on this repository because it is read-only and " \
                    "the svc:/application/pkg/server instance does not have " \
                    "a config/writable_root SMF property set. " \
                    "Request was: {0}".format(self.request)


class BackgroundTask(object):
        """Allow us to process a limited set of threads in the background."""

        def __init__(self, size=10, busy_url=None):
                self.size = size
                self.__q = queue.Queue(self.size)
                self.__thread = None
                self.__running = False
                self.__keep_busy_thread = None
                self.__keep_busy = False
                self.__busy_url = busy_url

        def join(self):
                """perform a Queue.join(), which blocks until all the tasks
                in the queue have been completed."""
                self.__q.join()

        def unfinished_tasks(self):
                """Return the number of tasks remaining in our Queue."""
                return self.__q.unfinished_tasks

        def put(self, task, *args, **kwargs):
                """Schedule the given task for background execution if queue
                isn't full.
                """
                if self.__q.unfinished_tasks > self.size - 1:
                        raise queue.Full()
                self.__q.put_nowait((task, args, kwargs))
                self.__keep_busy = True

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
                                        if self.__q.unfinished_tasks == 0:
                                                self.__keep_busy = False
                        except Exception as e:
                                print("Failure encountered executing "
                                    "background task {0!r}.".format(self))

        def run_keep_busy(self):
                """Run our keep_busy thread, periodically sending a HTTP
                request if the __keep_busy flag is set."""
                while self.__running:
                        # wait for a period of time, then ping our busy_url
                        time.sleep(KEEP_BUSY_INTERVAL)
                        if self.__keep_busy:
                                try:
                                        urlopen(self.__busy_url).close()
                                except Exception as e:
                                        print("Failure encountered retrieving "
                                            "busy url {0}: {1}".format(
                                            self.__busy_url, e))

        def start(self):
                """Start the background task thread. Since we configure
                mod_wsgi with an inactivity-timeout, long-running background
                tasks which don't cause new WSGI HTTP requests can
                result in us hitting that inactivity-timeout. To prevent this,
                while background tasks are running, we periodically send a HTTP
                request to the server."""
                self.__running = True
                if not self.__thread:
                        # Create and start a thread for the caller.
                        self.__thread = threading.Thread(target=self.run)
                        self.__thread.start()

                        self.__keep_busy_thread = threading.Thread(
                            target=self.run_keep_busy)
                        self.__keep_busy_thread.start()


class DepotBUI(object):
        """A data object that pkg.server.face can use for configuration.
        This object should look like a pkg.server.depot.DepotHTTP to
        pkg.server.face, but it doesn't need to perform any operations.

        pkg5_test_proto should point to a proto area where we can access
        web resources (css, html, etc)
        """

        def __init__(self, repo, dconf, writable_root, pkg5_test_proto=""):
                self.repo = repo
                self.cfg = dconf
                if writable_root:
                        self.tmp_root = writable_root
                else:
                        self.tmp_root = tempfile.mkdtemp(prefix="pkg-depot.")
                        # try to clean up the temporary area on exit
                        atexit.register(shutil.rmtree, self.tmp_root,
                            ignore_errors=True)

                # we hardcode these for the depot.
                self.content_root = "{0}/usr/share/lib/pkg".format(pkg5_test_proto)
                self.web_root = "{0}/usr/share/lib/pkg/web/".format(pkg5_test_proto)

                # ensure we have the right values in our cfg, needed when
                # creating DepotHTTP objects.
                self.cfg.set_property("pkg", "content_root", self.content_root)
                self.cfg.set_property("pkg", "pkg_root", self.repo.root)
                self.cfg.set_property("pkg", "writable_root", self.tmp_root)
                face.init(self)


class WsgiDepot(object):
        """A WSGI application object that allows us to process search/1 and
        certain admin/0 requests from pkg(5) clients of the depot.  Other
        requests for BUI content are dealt with by instances of DepotHTTP, which
        are created as necessary.

        In the server-side WSGI environment, apart from the default WSGI
        values, defined in PEP333, we expect the following:

        PKG5_RUNTIME_DIR  A directory that contains runtime state, notably
                          a htdocs/ directory.

        PKG5_REPOSITORY_<repo_prefix> A path to the repository root for the
                          given <repo_prefix>.  <repo_prefix> is a unique
                          alphanumeric prefix for the depot, each corresponding
                          to a given <repo_root>.  Many PKG5_REPOSITORY_*
                          variables can be configured, possibly containing
                          pkg5 publishers of the same name.

        PKG5_WRITABLE_ROOT_<repo_prefix> A path to the writable root for the
                          given <repo_prefix>. If a writable root is not set,
                          and a search index does not already exist in the
                          repository root, search functionality is not
                          available.

        PKG5_ALLOW_REFRESH Set to 'true', this determines whether we process
                          admin/0 requests that have the query 'cmd=refresh' or
                          'cmd=refresh-indexes'.

                          If not true, we return a HTTP 503 response. Otherwise,
                          we start a server-side job that rebuilds the
                          index for the given repository.  Catalogs are not
                          rebuilt by 'cmd=rebuild' queries, since this
                          application only supports 'pkg/readonly' instances
                          of svc:/application/pkg/depot.

        PKG5_TEST_PROTO   If set, this points at the top of a proto area, used
                          to ensure the WSGI application uses files from there
                          rather than the test system.  This is only used when
                          running the pkg5 test suite for depot_index.py
        """

        def __init__(self):
                self.bgtask = None

        def setup(self, request):
                """Builds a dictionary of sr.Repository objects, keyed by the
                repository prefix, and ensures our search indexes exist."""

                def get_repo_paths():
                        """Return a dictionary of repository paths, and writable
                        root directories for the repositories we're serving."""

                        repo_paths = {}
                        for key in request.wsgi_environ:
                                if key.startswith("PKG5_REPOSITORY"):
                                        prefix = key.replace("PKG5_REPOSITORY_",
                                            "")
                                        repo_paths[prefix] = \
                                            request.wsgi_environ[key]
                                        writable_root = \
                                            request.wsgi_environ.get(
                                            "PKG5_WRITABLE_ROOT_{0}".format(prefix))
                                        repo_paths[prefix] = \
                                            (request.wsgi_environ[key],
                                            writable_root)
                        return repo_paths

                if repositories:
                        return

                # if running the pkg5 test suite, store the correct proto area
                pkg5_test_proto = request.wsgi_environ.get("PKG5_TEST_PROTO",
                    "")

                repository_lock.acquire()
                repo_paths = get_repo_paths()

                # We must ensure our BackgroundTask object has at least as many
                # slots available as we have repositories, to allow the indexes
                # to be refreshed. Ideally, we'd also account for a slot
                # per-publisher, per-repository, but that might be overkill on a
                # system with many repositories and many publishers that rarely
                # get 'pkgrepo refresh' requests.
                self.bgtask = BackgroundTask(len(repo_paths),
                    busy_url="{0}/depot/depot-keepalive".format(request.base))
                self.bgtask.start()

                for prefix in repo_paths:
                        path, writable_root = repo_paths[prefix]
                        try:
                                repo = sr.Repository(root=path, read_only=True,
                                    writable_root=writable_root)
                        except sr.RepositoryError as e:
                                print("Unable to load repository: {0}".format(e))
                                continue

                        repositories[prefix] = repo
                        dconf = sd.DepotConfig()
                        if writable_root is not None:
                                self.bgtask.put(repo.refresh_index)

                        depot = DepotBUI(repo, dconf, writable_root,
                            pkg5_test_proto=pkg5_test_proto)
                        depot_buis[prefix] = depot

                repository_lock.release()

        def get_accept_lang(self, request, depot_bui):
                """Determine a language that this accept can request that we
                also have templates for."""

                rlangs = []
                for entry in request.headers.elements("Accept-Language"):
                        rlangs.append(str(entry).split(";")[0])
                for rl in rlangs:
                        if os.path.exists(os.path.join(depot_bui.web_root, rl)):
                                return rl
                return "en"

        def repo_index(self, *tokens, **params):
                """Generate a page showing the list of repositories served by
                this Apache instance."""

                self.setup(cherrypy.request)
                # In order to reuse the pkg.depotd shtml files, we need to use
                # the pkg.server.api, which means passing a DepotBUI object,
                # despite the fact that we're not serving content for any one
                # repository.  For the purposes of rendering this page, we'll
                # use the first object we come across.
                depot = depot_buis[list(depot_buis.keys())[0]]
                accept_lang = self.get_accept_lang(cherrypy.request, depot)
                cherrypy.request.path_info = "/{0}".format(accept_lang)
                tlookup = mako.lookup.TemplateLookup(
                    directories=[depot.web_root])
                pub = None
                base = pkg.server.api.BaseInterface(cherrypy.request, depot,
                    pub)

                # build a list of all repositories URIs and BUI links,
                # and a dictionary of publishers for each repository URI
                repo_list = []
                repo_pubs = {}
                for repo_prefix in repositories.keys():
                        repo = repositories[repo_prefix]
                        depot = depot_buis[repo_prefix]
                        repo_url = "{0}/{1}".format(cherrypy.request.base,
                            repo_prefix)
                        bui_link = "{0}/{1}/index.shtml".format(
                            repo_prefix, accept_lang)
                        repo_list.append((repo_url, bui_link))
                        repo_pubs[repo_url] = \
                            [(pub, "{0}/{1}/{2}".format(
                            cherrypy.request.base, repo_prefix,
                            pub)) for pub in repo.publishers]
                repo_list.sort()
                template = tlookup.get_template("repos.shtml")
                # Starting in CherryPy 3.2, cherrypy.response.body only allows
                # bytes.
                return misc.force_bytes(template.render(g_vars={"base": base,
                    "pub": None, "http_depot": "true", "lang": accept_lang,
                    "repo_list": repo_list, "repo_pubs": repo_pubs
                    }))

        def default(self, *tokens, **params):
                """ Our default handler is here to make sure we've called
                setup, grabbing configuration from httpd.conf, then redirecting.
                It also knows whether a request should be passed off to the
                BUI, or whether we can just report an error."""

                self.setup(cherrypy.request)

                def request_pub_func(path):
                        """Return the name of the publisher to be used
                        for a given path. This function intentionally
                        returns None for all paths."""
                        return None

                if "_themes" in tokens:
                        # manipulate the path to remove everything up to _themes
                        theme_index = tokens.index("_themes")
                        cherrypy.request.path_info = "/".join(
                            tokens[theme_index:])
                        # When serving  theme resources we just choose the first
                        # repository we find, which is fine since we're serving
                        # content that's generic to all repositories, so we
                        repo_prefix = list(repositories.keys())[0]
                        repo = repositories[repo_prefix]
                        depot_bui = depot_buis[repo_prefix]
                        # use our custom request_pub_func, since theme resources
                        # are not publisher-specific
                        dh = sd.DepotHTTP(repo, depot_bui.cfg,
                            request_pub_func=request_pub_func)
                        return dh.default(*tokens[theme_index:])

                elif tokens[0] not in repositories:
                        raise cherrypy.NotFound()

                # Otherwise, we'll try to serve the request from the BUI.

                repo_prefix = tokens[0]
                depot_bui = depot_buis[repo_prefix]
                repo = repositories[repo_prefix]
                # when serving reources, the publisher is not used
                # to locate templates, so use our custom
                # request_pub_func
                dh = sd.DepotHTTP(repo, depot_bui.cfg,
                    request_pub_func=request_pub_func)

                # trim the repo_prefix
                cherrypy.request.path_info = re.sub("^/{0}".format(repo_prefix),
                    "", cherrypy.request.path_info)

                accept_lang = self.get_accept_lang(cherrypy.request,
                    depot_bui)
                path = cherrypy.request.path_info.rstrip("/").lstrip("/")
                toks = path.split("/")
                pub = None

                # look for a publisher in the path
                if toks[0] in repo.publishers:
                        path = "/".join(toks[1:])
                        pub = toks[0]
                        toks = self.__strip_pub(toks, repo)
                        cherrypy.request.path_info = "/".join(toks)

                # deal with users browsing directories
                dirs = ["", accept_lang, repo_prefix]
                if path in dirs:
                        if not pub:
                                raise cherrypy.HTTPRedirect(
                                    "/{0}/{1}/index.shtml".format(
                                    repo_prefix, accept_lang))
                        else:
                                raise cherrypy.HTTPRedirect(
                                    "/{0}/{1}/{2}/index.shtml".format(
                                    repo_prefix, pub, accept_lang))

                resp = face.respond(depot_bui, cherrypy.request,
                    cherrypy.response, pub, http_depot=repo_prefix)
                return resp

        def manifest(self, *tokens):
                """Manifest requests coming from the BUI need to be redirected
                back through the RewriteRules defined in the Apache
                configuration in order to be served directly.
                pkg(1) will never hit this code, as those requests don't get
                handled by this webapp.
                """

                self.setup(cherrypy.request)
                rel_uri = cherrypy.request.path_info

                # we need to recover the escaped portions of the URI
                redir = rel_uri.lstrip("/").split("/")
                pub_mf = "/".join(redir[0:4])
                pkg_name = "/".join(redir[4:])
                # encode the URI so our RewriteRules can process them
                pkg_name = quote(pkg_name)
                pkg_name = pkg_name.replace("/", "%2F")
                pkg_name = pkg_name.replace("%40", "@", 1)

                # build a URI that we can redirect to
                redir = "{0}/{1}".format(pub_mf, pkg_name)
                redir = "/{0}".format(redir.lstrip("/"))
                raise cherrypy.HTTPRedirect(redir)

        def __build_depot_http(self):
                """Build a DepotHTTP object to handle the current request."""
                self.setup(cherrypy.request)
                headers = cherrypy.response.headers
                headers["Content-Type"] = "text/plain; charset=utf-8"

                toks = cherrypy.request.path_info.lstrip("/").split("/")
                repo_prefix = toks[0]
                if repo_prefix not in repositories:
                        raise cherrypy.NotFound()

                repo = repositories[repo_prefix]
                depot_bui = depot_buis[repo_prefix]
                if repo_prefix in depot_https:
                        return depot_https[repo_prefix]

                def request_pub_func(path_info):
                        """A function that can be called to determine the
                        publisher for a given request. We always want None
                        here, to force DepotHTTP to fallback to the publisher
                        information in the FMRI provided as part of the request,
                        rather than the /publisher/ portion of path_info.
                        """
                        return None

                depot_https[repo_prefix] = sd.DepotHTTP(repo, depot_bui.cfg,
                    request_pub_func=request_pub_func)
                return depot_https[repo_prefix]

        def __strip_pub(self, tokens, repo):
                """Attempt to strip at most one publisher from the path
                described by 'tokens' looking for the publishers configured
                in 'repo', returning new tokens."""

                if len(tokens) <= 0:
                        return tokens
                stripped = False
                # For our purposes, the first token is always the repo_prefix
                # indicating which repository we're talking to.
                new_tokens = [tokens[0]]
                for t in tokens[1:]:
                        if t in repo.publishers and not stripped:
                                stripped = True
                                pass
                        else:
                                new_tokens.append(t)
                return new_tokens

        def info(self, *tokens):
                """Use a DepotHTTP to return an info response."""

                dh = self.__build_depot_http()
                tokens = self.__strip_pub(tokens, dh.repo)
                return dh.info_0(*tokens[3:])

        def p5i(self, *tokens):
                """Use a DepotHTTP to return a p5i response."""

                dh = self.__build_depot_http()
                tokens = self.__strip_pub(tokens, dh.repo)
                headers = cherrypy.response.headers
                headers["Content-Type"] = pkg.p5i.MIME_TYPE
                return dh.p5i_0(*tokens[3:])

        def search_1(self, *tokens, **params):
                """Use a DepotHTTP to return a search/1 response."""

                toks = cherrypy.request.path_info.lstrip("/").split("/")
                dh = self.__build_depot_http()
                toks = self.__strip_pub(tokens, dh.repo)
                query_str = "/".join(toks[3:])
                return dh.search_1(query_str)

        def search_0(self, *tokens):
                """Use a DepotHTTP to return a search/0 response."""

                toks = cherrypy.request.path_info.lstrip("/").split("/")
                dh = self.__build_depot_http()
                toks = self.__strip_pub(tokens, dh.repo)
                return dh.search_0(toks[-1])

        def admin(self, *tokens, **params):
                """ We support limited admin/0 operations.  For a repository
                refresh, we only honor the index rebuild itself.

                Since a given http-depot server may be serving many repositories
                we expend a little more effort than pkg.server.depot when
                accepting refresh requests when our existing BackgroundTask
                Queue is full, retrying jobs for up to a minute.  In the future,
                we may want to make the Queue scale according to the size of the
                depot/repository.
                """
                self.setup(cherrypy.request)
                request = cherrypy.request
                cmd = params.get("cmd")
                if not cmd:
                        return
                if cmd not in ["refresh", "refresh-indexes"]:
                        raise AdminOpNotSupportedException(
                            request.wsgi_environ["REQUEST_URI"], cmd)

                # Determine whether to allow index rebuilds
                if request.wsgi_environ.get(
                    "PKG5_ALLOW_REFRESH", "false").lower() != "true":
                        raise AdminOpsDisabledException(
                            request.wsgi_environ["REQUEST_URI"])

                repository_lock.acquire()
                try:
                        if len(tokens) <= 2:
                                raise cherrypy.NotFound()
                        repo_prefix = tokens[0]
                        pub_prefix = tokens[1]

                        if repo_prefix not in repositories:
                                raise cherrypy.NotFound()

                        repo = repositories[repo_prefix]
                        if pub_prefix not in repo.publishers:
                                raise cherrypy.NotFound()

                        # Since the repository is read-only, we only honour
                        # index refresh requests if we have a writable root.
                        if not repo.writable_root:
                                raise IndexOpDisabledException(
                                    request.wsgi_environ["REQUEST_URI"])

                        # we need to reload the repository in order to get
                        # any new catalog contents before refreshing the
                        # index.
                        repo.reload()
                        try:
                                self.bgtask.put(repo.refresh_index,
                                    pub=pub_prefix)
                        except queue.Full as e:
                                retries = 10
                                success = False
                                while retries > 0 and not success:
                                        time.sleep(5)
                                        try:
                                                self.bgtask.put(
                                                    repo.refresh_index,
                                                    pub=pub_prefix)
                                                success = True
                                        except Exception as ex:
                                                pass
                                if not success:
                                        raise cherrypy.HTTPError(
                                            status=http_client.SERVICE_UNAVAILABLE,
                                            message="Unable to refresh the "
                                            "index for {0} after repeated "
                                            "retries. Try again later.".format(
                                            request.path_info))
                finally:
                        repository_lock.release()
                return ""

        def wait_refresh(self, *tokens, **params):
                """Not a pkg(5) operation, this allows clients to wait until any
                pending index refresh operations have completed.

                This method exists primarily for the pkg(5) test suite to ensure
                that we do not attempt to perform searches when the server is
                still coming up.
                """
                self.setup(cherrypy.request)
                self.bgtask.join()
                return ""


class Pkg5Dispatch(object):
        """A custom CherryPy dispatcher used by our application.
        We use this, because the default dispatcher in CherryPy seems to dislike
        trying to have an exposed "default" method (the special method name used
        by CherryPy in its default dispatcher to handle unmapped resources) as
        well as trying to serve resources named "default", a common name for
        svc:/application/pkg/server SMF instances, which become the names of the
        repo_prefixes used by the http-depot.
        """

        def __init__(self, wsgi_depot):
                self.app = wsgi_depot
                # needed to convince CherryPy that we are a valid dispatcher
                self.config = {}

        @staticmethod
        def default_error_page(status=http_client.NOT_FOUND, message="oops",
            traceback=None, version=None):
                """This function is registered as the default error page
                for CherryPy errors.  This sets the response headers to
                be uncacheable, and then returns a HTTP response."""

                response = cherrypy.response
                for key in ('Cache-Control', 'Pragma'):
                        if key in response.headers:
                                del response.headers[key]

                # Server errors are interesting, so let's log them.  In the case
                # of an internal server error, we send a 404 to the client. but
                # log the full details in the server log.
                if (status == http_client.INTERNAL_SERVER_ERROR or
                    status.startswith("500 ")):
                        # Convert the error to a 404 to obscure implementation
                        # from the client, but log the original error to the
                        # server logs.
                        error = cherrypy._cperror._HTTPErrorTemplate % \
                            {"status": http_client.NOT_FOUND,
                            "message": http_client.responses[http_client.NOT_FOUND],
                            "traceback": "",
                            "version": cherrypy.__version__}
                        print("Path that raised exception was {0}".format(
                            cherrypy.request.path_info))
                        print(message)
                        return error
                else:
                        error = cherrypy._cperror._HTTPErrorTemplate % \
                            {"status": http_client.NOT_FOUND, "message": message,
                            "traceback": "", "version": cherrypy.__version__}
                        return error

        def dispatch(self, path_info):
                request = cherrypy.request
                request.config = {}
                request.error_page["default"] = Pkg5Dispatch.default_error_page

                toks = path_info.lstrip("/").split("/")
                params = request.params
                if not params:
                        try:
                                # Starting in CherryPy 3.2, it seems that
                                # query_string doesn't pass into request.params,
                                # so try harder here.
                                from cherrypy.lib.httputil import parse_query_string
                                params = parse_query_string(
                                    request.query_string)
                                request.params.update(params)
                        except ImportError:
                                pass
                file_type = toks[-1].split(".")[-1]

                try:
                        if "/search/1/" in path_info:
                                cherrypy.response.stream = True
                                cherrypy.response.body = self.app.search_1(
                                    *toks, **params)
                        elif "/search/0/" in path_info:
                                cherrypy.response.stream = True
                                cherrypy.response.body = self.app.search_0(
                                    *toks)
                        elif "/manifest/0/" in path_info:
                                cherrypy.response.body = self.app.manifest(
                                    *toks)
                        elif "/info/0/" in path_info:
                                cherrypy.response.body = self.app.info(*toks,
                                    **params)
                        elif "/p5i/0/" in path_info:
                                cherrypy.response.body = self.app.p5i(*toks,
                                    **params)
                        elif "/admin/0" in path_info:
                                cherrypy.response.body = self.app.admin(*toks,
                                    **params)
                        elif "/depot-keepalive" in path_info:
                                return ""
                        elif "/depot-wait-refresh" in path_info:
                                self.app.wait_refresh(*toks, **params)
                                return ""
                        elif path_info == "/" or path_info == "/repos.shtml":
                                cherrypy.response.body = self.app.repo_index(
                                    *toks, **params)
                        elif file_type in ["css", "shtml", "png"]:
                                cherrypy.response.body = self.app.default(*toks,
                                    **params)
                        else:
                                cherrypy.response.body = self.app.default(*toks,
                                    **params)
                except Exception as e:
                        if isinstance(e, cherrypy.HTTPRedirect):
                                raise
                        elif isinstance(e, cherrypy.HTTPError):
                                raise
                        elif isinstance(e, AdminOpsDisabledException):
                                raise cherrypy.HTTPError(e.http_status,
                                    "This operation has been disabled by the "
                                    "server administrator.")
                        elif isinstance(e, AdminOpNotSupportedException):
                                raise cherrypy.HTTPError(e.http_status,
                                    "This operation is not supported.")
                        elif isinstance(e, IndexOpDisabledException):
                                raise cherrypy.HTTPError(e.http_status,
                                    "This operation has been disabled by the "
                                    "server administrator.")
                        else:
                                # we leave this as a 500 for now. It will be
                                # converted and logged by our error handler
                                # before the client sees it.
                                raise cherrypy.HTTPError(
                                    status=http_client.INTERNAL_SERVER_ERROR,
                                    message="".join(traceback.format_exc(e)))

wsgi_depot = WsgiDepot()
dispatcher = Pkg5Dispatch(wsgi_depot)

conf = {"/":
    {'request.dispatch': dispatcher.dispatch}}
application = cherrypy.Application(wsgi_depot, None, config=conf)
# Raise the level of the access log to make it quiet. For some reason,
# setting log.access_file = "" or None doesn't work.
application.log.access_log.setLevel(logging.WARNING)
