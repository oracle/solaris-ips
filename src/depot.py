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

# The default authority for the depot.
AUTH_DEFAULT = "opensolaris.org"
# The default repository path.
REPO_PATH_DEFAULT = "/var/pkg/repo"
# The default port to serve data from.
PORT_DEFAULT = 80
# The minimum number of threads allowed.
THREADS_MIN = 1
# The default number of threads to start.
THREADS_DEFAULT = 10
# The maximum number of threads that can be started.
THREADS_MAX = 100
# The default server socket timeout in seconds. We want this to be longer than
# the normal default of 10 seconds to accommodate clients with poor quality
# connections.
SOCKET_TIMEOUT_DEFAULT = 60
# Whether modify operations should be allowed.
READONLY_DEFAULT = False
# Whether the repository catalog should be rebuilt on startup.
REBUILD_DEFAULT = False
# Whether the indexes should be rebuilt
REINDEX_DEFAULT = False

import getopt
import os
import sys
import urlparse

try:
        import cherrypy
        version = cherrypy.__version__.split('.')
        if map(int, version) < [3, 0, 3]:
                raise ImportError
        elif map(int, version) >= [3, 1, 0]:
                raise ImportError
except ImportError:
        print """cherrypy 3.0.3 or greater (but less than 3.1.0) is """ \
            """required to use this program."""
        sys.exit(2)

import pkg.server.face as face
import pkg.server.config as config
import pkg.server.depot as depot
import pkg.server.repository as repo
import pkg.server.repositoryconfig as rc
from pkg.misc import port_available, emsg

def usage():
        print """\
Usage: /usr/lib/pkg.depotd [--readonly] [--rebuild] [--proxy-base url]
           [-d repo_dir] [-p port] [-s threads] [-t socket_timeout] 

        --readonly      Read-only operation; modifying operations disallowed
        --rebuild       Re-build the catalog from pkgs in depot
                        Cannot be used with --readonly
        --proxy-base    The url to use as the base for generating internal
                        redirects and content.
"""
        sys.exit(2)

class OptionError(Exception):
        """Option exception. """

        def __init__(self, *args):
                Exception.__init__(self, *args)

if __name__ == "__main__":

        port = PORT_DEFAULT
        threads = THREADS_DEFAULT
        socket_timeout = SOCKET_TIMEOUT_DEFAULT
        readonly = READONLY_DEFAULT
        rebuild = REBUILD_DEFAULT
        reindex = REINDEX_DEFAULT
        proxy_base = None

        if "PKG_REPO" in os.environ:
                repo_path = os.environ["PKG_REPO"]
        else:
                repo_path = REPO_PATH_DEFAULT

        try:
                parsed = set()
                opts, pargs = getopt.getopt(sys.argv[1:], "d:np:s:t:",
                    ["readonly", "rebuild", "proxy-base=", "refresh-index"])
                opt = None
                for opt, arg in opts:
                        if opt in parsed:
                                raise OptionError, "Each option may only be " \
                                    "specified once."
                        else:
                                parsed.add(opt)

                        if opt == "-n":
                                sys.exit(0)
                        elif opt == "-d":
                                repo_path = arg
                        elif opt == "-p":
                                port = int(arg)
                        elif opt == "-s":
                                threads = int(arg)
                                if threads < THREADS_MIN:
                                        raise OptionError, \
                                            "minimum value is %d" % THREADS_MIN
                                if threads > THREADS_MAX:
                                        raise OptionError, \
                                            "maximum value is %d" % THREADS_MAX
                        elif opt == "-t":
                                socket_timeout = int(arg)
                        elif opt == "--readonly":
                                readonly = True
                        elif opt == "--rebuild":
                                rebuild = True
                        elif opt == "--refresh-index":
                                # Note: This argument is for internal use
                                # only. It's used when pkg.depotd is reexecing
                                # itself and needs to know that's the case.
                                # This flag is purposefully omitted in usage.
                                # The supported way to forcefully reindex is to
                                # kill any pkg.depot using that directory,
                                # remove the index directory, and restart the
                                # pkg.depot process. The index will be rebuilt
                                # automatically on startup.
                                reindex = True
                        elif opt == "--proxy-base":
                                # Attempt to decompose the url provided into
                                # its base parts.  This is done so we can
                                # remove any scheme information since we
                                # don't need it.
                                scheme, netloc, path, params, query, \
                                    fragment = urlparse.urlparse(arg,
                                    allow_fragments=0)

                                # Rebuild the url without the scheme and
                                # remove the leading // urlunparse adds.
                                proxy_base = urlparse.urlunparse(("", netloc,
                                    path, params, query, fragment)
                                    ).lstrip("//")

        except getopt.GetoptError, e:
                print "pkg.depotd: %s" % e.msg
                usage()
        except OptionError, e:
                print "pkg.depotd: option: %s -- %s" % (opt, e)
                usage()
        except (ArithmeticError, ValueError):
                print "pkg.depotd: illegal option value: %s specified " \
                    "for option: %s" % (arg, opt)
                usage()

        if rebuild and reindex:
                print "--refresh-index cannot be used with --rebuild"
                usage()
        if rebuild and readonly:
                print "--readonly cannot be used with --rebuild"
                usage()
        if reindex and readonly:
                print "--readonly cannot be used with --refresh-index"
                usage()

        # If the program is going to reindex, the port is irrelevant since
        # the program will not bind to a port.
        if not reindex:
                available, msg = port_available(None, port)
                if not available:
                        print "pkg.depotd: unable to bind to the specified " \
                            "port: %d. Reason: %s" % (port, msg)
                        sys.exit(1)

        try:
                face.set_content_root(os.environ["PKG_DEPOT_CONTENT"])
        except KeyError:
                pass

        scfg = config.SvrConfig(repo_path, AUTH_DEFAULT)

        if rebuild:
                scfg.destroy_catalog()

        if readonly:
                scfg.set_read_only()

        try:
                scfg.init_dirs()
        except EnvironmentError, e:
                print "pkg.depotd: an error occurred while trying to " \
                    "initialize the depot repository directory " \
                    "structures:\n%s" % e
                sys.exit(1)

        if reindex:
                scfg.acquire_catalog(rebuild=False)
                scfg.catalog.run_update_index()
                sys.exit(0)

        scfg.acquire_in_flight()
        scfg.acquire_catalog()

        try:
                root = cherrypy.Application(repo.Repository(scfg))
        except rc.InvalidAttributeValueError, e:
                emsg("pkg.depotd: repository.conf error: %s" % e)
                sys.exit(1)

        # We have to override cherrypy's default response_class so that we
        # have access to the write() callable to stream data directly to the
        # client.
        root.wsgiapp.response_class = depot.DepotResponse

        # Setup our basic server configuration.
        cherrypy.config.update({
            "environment": "production",
            "checker.on": True,
            "log.screen": True,
            "server.socket_port": port,
            "server.thread_pool": threads,
            "server.socket_timeout": socket_timeout
        })

        # Now build our site configuration.
        conf = {
            "/robots.txt": {
                "tools.staticfile.on": True,
                "tools.staticfile.filename": os.path.join(face.content_root,
                    "robots.txt")
            },
            "/static": {
                "tools.staticdir.on": True,
                "tools.staticdir.root": face.content_root,
                "tools.staticdir.dir": ""
            }
        }

        if proxy_base:
                # This changes the base URL for our server, and is primarily
                # intended to allow our depot process to operate behind Apache
                # or some other webserver process.
                #
                # Visit the following URL for more information:
                #    http://cherrypy.org/wiki/BuiltinTools#tools.proxy
                proxy_conf = {
                        "tools.proxy.on": True,
                        "tools.proxy.local": "",
                        "tools.proxy.base": proxy_base
                }

                if "/" not in conf:
                        conf["/"] = {}

                # Now merge or add our proxy configuration information into the
                # existing configuration.
                for entry in proxy_conf:
                        conf["/"][entry] = proxy_conf[entry]

        try:
                cherrypy.quickstart(root, config = conf)
        except:
                print "pkg.depotd: unknown error starting depot, illegal " \
                    "option value specified?"
                usage()

