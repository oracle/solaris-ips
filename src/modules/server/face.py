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
# Copyright (c) 2007, 2015, Oracle and/or its affiliates. All rights reserved.
#

"""face - provides the BUI (Browser User Interface) for the image packaging
server"""

from __future__ import print_function
import cherrypy
import cherrypy.lib.static
import os
import sys

from six.moves import http_client
from six.moves.urllib.parse import unquote

import pkg.misc as misc
import pkg.server.api as api
import pkg.server.api_errors as sae
import pkg.server.feed

try:
        import mako.exceptions
        import mako.lookup
except ImportError:
        # Can't actually perform a version check since Mako doesn't provide
        # version information, but this is what should be used currently.
        print("Mako 0.2.2 or greater is required to use this program.",
            file=sys.stderr)
        sys.exit(2)

tlookup = None
def init(depot):
        """Ensure that the BUI is properly initialized."""
        global tlookup
        pkg.server.feed.init(depot)
        tlookup = mako.lookup.TemplateLookup(directories=[depot.web_root])

def feed(depot, request, response, pub):
        if depot.repo.mirror:
                raise cherrypy.HTTPError(http_client.NOT_FOUND,
                    "Operation not supported in current server mode.")
        if not depot.repo.get_catalog(pub).updates:
                raise cherrypy.HTTPError(http_client.SERVICE_UNAVAILABLE,
                    "No update history; unable to generate feed.")
        return pkg.server.feed.handle(depot, request, response, pub)

def __render_template(depot, request, path, pub, http_depot=None):
        template = tlookup.get_template(path)
        base = api.BaseInterface(request, depot, pub)
        # Starting in CherryPy 3.2, cherrypy.response.body only allows
        # bytes.
        return misc.force_bytes(template.render(g_vars={ "base": base,
            "pub": pub, "http_depot": http_depot}))

def __handle_error(path, error):
        # All errors are treated as a 404 since reverse proxies such as Apache
        # don't handle 500 errors in a desirable way.  For any error but a 404,
        # an error is logged.
        if error != http_client.NOT_FOUND:
                cherrypy.log("Error encountered while processing "
                    "template: {0}\n".format(path), traceback=True)

        raise cherrypy.NotFound()

def respond(depot, request, response, pub, http_depot=None):
        """'http_depot' if set should be the resource that points to the top
        level of repository being served (referred to as the repo_prefix in
        depot_index.py)"""
        path = request.path_info.strip("/")
        if pub and os.path.exists(os.path.join(depot.web_root, pub)):
                # If an item exists under the web root
                # with this name, it isn't a publisher
                # prefix.
                pub = None
        elif pub and pub not in depot.repo.publishers:
                raise cherrypy.NotFound()

        if pub:
                # Strip publisher from path as it can't be used to determine
                # resource locations.
                path = path.replace(pub, "").strip("/")
        else:
                # No publisher specified in request, so assume default.
                pub = depot.repo.cfg.get_property("publisher", "prefix")
                if not pub:
                        pub = None

        if path == "":
                path = "index.shtml"
        elif path.split("/")[0] == "feed":
                response.headers.update({ "Expires": 0, "Pragma": "no-cache",
                    "Cache-Control": "no-cache, no-transform, must-revalidate"
                    })
                return feed(depot, request, response, pub)

        if not path.endswith(".shtml"):
                spath = unquote(path)
                fname = os.path.join(depot.web_root, spath)
                if not os.path.normpath(fname).startswith(
                    os.path.normpath(depot.web_root)):
                        # Ignore requests for files outside of the web root.
                        return __handle_error(path, http_client.NOT_FOUND)
                else:
                        return cherrypy.lib.static.serve_file(os.path.join(
                            depot.web_root, spath))

        try:
                response.headers.update({ "Expires": 0, "Pragma": "no-cache",
                    "Cache-Control": "no-cache, no-transform, must-revalidate"
                    })
                return __render_template(depot, request, path, pub, http_depot)
        except sae.VersionException as e:
                # The user shouldn't see why we can't render a template, but
                # the reason should be logged (cleanly).
                cherrypy.log("Template '{path}' is incompatible with current "
                    "server api: {error}".format(path=path,
                    error=str(e)))
                cherrypy.log("Ensure that the correct --content-root has been "
                    "provided to pkg.depotd.")
                return __handle_error(request.path_info, http_client.NOT_FOUND)
        except IOError as e:
                return __handle_error(path, http_client.INTERNAL_SERVER_ERROR)
        except mako.exceptions.TemplateLookupException as e:
                # The above exception indicates that mako could not locate the
                # template (in most cases, Mako doesn't seem to always clearly
                # differentiate).
                return __handle_error(path, http_client.NOT_FOUND)
        except sae.RedirectException as e:
                raise cherrypy.HTTPRedirect(e.data)
        except:
                return __handle_error(path, http_client.INTERNAL_SERVER_ERROR)
