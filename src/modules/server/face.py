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
# Copyright (c) 2007, 2010, Oracle and/or its affiliates. All rights reserved.
#

"""face - provides the BUI (Browser User Interface) for the image packaging server"""

import cherrypy
import cherrypy.lib.static
import httplib
import os
import pkg.server.api as api
import pkg.server.api_errors as sae
import pkg.server.feed
import sys
import urllib
try:
        import mako.exceptions
        import mako.lookup
except ImportError:
        # Can't actually perform a version check since Mako doesn't provide
        # version information, but this is what should be used currently.
        print >> sys.stderr, "Mako 0.2.2 or greater is required to use this " \
            "program."
        sys.exit(2)

tlookup = None
def init(repo, web_root):
        """Ensure that the BUI is properly initialized."""
        global tlookup
        pkg.server.feed.init(repo)
        tlookup = mako.lookup.TemplateLookup(directories=[web_root])

def feed(repo, request, response):
        if repo.mirror:
                raise cherrypy.HTTPError(httplib.NOT_FOUND,
                    "Operation not supported in current server mode.")
        if not repo.catalog.updates:
                raise cherrypy.HTTPError(httplib.SERVICE_UNAVAILABLE,
                    "No update history; unable to generate feed.")
        return pkg.server.feed.handle(repo, request, response)

def __render_template(repo, content_root, web_root, request, path):
        template = tlookup.get_template(path)
        base = api.BaseInterface(request, repo, content_root=content_root,
            web_root=web_root)
        return template.render_unicode(g_vars={ "base": base })

def __handle_error(path, error):
        # All errors are treated as a 404 since reverse proxies such as Apache
        # don't handle 500 errors in a desirable way.  For any error but a 404,
        # an error is logged.
        if error != httplib.NOT_FOUND:
                cherrypy.log("Error encountered while processing "
                    "template: %s\n" % path, traceback=True)

        raise cherrypy.NotFound()

def respond(repo, content_root, web_root, request, response):
        path = request.path_info.strip("/")
        if path == "":
                path = "index.shtml"
        elif path.split("/")[0] == "feed":
                response.headers.update({ "Expires": 0, "Pragma": "no-cache",
                    "Cache-Control": "no-cache, no-transform, must-revalidate" })
                return feed(repo, request, response)

        if not path.endswith(".shtml"):
                spath = urllib.unquote(path)
                fname = os.path.join(web_root, spath)
                if not os.path.normpath(fname).startswith(
                    os.path.normpath(web_root)):
                        # Ignore requests for files outside of the web root.
                        return __handle_error(path, httplib.NOT_FOUND)
                else:
                        return cherrypy.lib.static.serve_file(os.path.join(
                            web_root, spath))

        try:
                response.headers.update({ "Expires": 0, "Pragma": "no-cache",
                    "Cache-Control": "no-cache, no-transform, must-revalidate" })
                return __render_template(repo, content_root, web_root, request,
                    path)
        except sae.VersionException, e:
                # The user shouldn't see why we can't render a template, but
                # the reason should be logged (cleanly).
                cherrypy.log("Template '%(path)s' is incompatible with current "
                    "server api: %(error)s" % { "path": path,
                    "error": str(e) })
                cherrypy.log("Ensure that the correct --content-root has been "
                    "provided to pkg.depotd.")
                return __handle_error(request.path_info, httplib.NOT_FOUND)
        except IOError, e:
                return __handle_error(path, httplib.INTERNAL_SERVER_ERROR)
        except mako.exceptions.TemplateLookupException, e:
                # The above exception indicates that mako could not locate the
                # template (in most cases, Mako doesn't seem to always clearly
                # differentiate).
                return __handle_error(path, httplib.NOT_FOUND)
        except sae.RedirectException, e:
                raise cherrypy.HTTPRedirect(e.data)
        except:
                return __handle_error(path, httplib.INTERNAL_SERVER_ERROR)
