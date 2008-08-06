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

"""face - dynamic index page for image packaging server"""

import cherrypy
import httplib
import os

import pkg.server.feed
from pkg.misc import get_rel_path, get_res_path

# XXX Use small templating module?

try:
        content_root = os.path.join(os.environ['PKG_HOME'], 'share/lib/pkg')
except KeyError:
        content_root = '/usr/share/lib/pkg'

def init(scfg, rcfg):
        """Ensure that the BUI is properly initialized.
        """
        pkg.server.feed.init(scfg, rcfg)

def head(rcfg, request):
        """Returns the XHTML used as a common page header for depot pages."""
        return """\
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"
        "http://www.w3.org/TR/2002/REC-xhtml1-20020801/DTD/xhtml1-strict.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en">
<head>
 <link rel="shortcut icon" href="%s"/>
 <link rel="stylesheet" type="text/css" href="%s"/>
 <title>%s</title>
</head>
""" % (get_res_path(request, rcfg.get_attribute("repository", "icon")),
    get_res_path(request, rcfg.get_attribute("repository", "style")),
    rcfg.get_attribute("repository", "name"))

def unknown(scfg, rcfg, request, response):
        """Returns a response appropriate for unknown request paths."""

        response.status = httplib.NOT_FOUND
        output = head(rcfg, request)
        output += """\
<body>
 <div id="doc4" class="yui-t5">
  <div id="hd">
   <h1><img src="%s" alt="logo"/> <code>pkg</code> server unknown page: %s</h1>
  </div>
  <div id="bd">
   <div id="yui-main" class="yui-b">
    <pre>
""" % (get_res_path(request, rcfg.get_attribute("repository", "logo")),
    request.path_info)

        output += ('''%d GET URI %s ; headers:\n%s''' %
            (httplib.NOT_FOUND, request.path_info, request.headers))

        output += ("""\
    </pre>
   </div>
  </div>
 </div>
</body>
</html>
""")
        return output

def error(rcfg, request, response):
        """Returns an appropriate response for error conditions."""
        response.status = httplib.INTERNAL_SERVER_ERROR
        output = head(rcfg, request)
        output += """\
<body>
 <div id="doc4" class="yui-t5">
  <div id="hd">
   <h1><img src="%s" alt="logo"/> <code>pkg</code> server internal error</h1>
  </div>
  <div id="bd">
   <div id="yui-main" class="yui-b">
    <pre>    
face.response() for %s
    </pre>
   </div>
  </div>
 </div>
</body>
</html>
""" % (get_res_path(request, rcfg.get_attribute("repository", "logo")),
    request.path_info)

        return output

fmri_ops = {
    'info': "Info",
    'manifest': "Manifest"
}

def index(scfg, rcfg, request, response):
        """Returns a dynamically-generated status page for the repository
        represented by scfg."""

        output = """\
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"
        "http://www.w3.org/TR/2002/REC-xhtml1-20020801/DTD/xhtml1-strict.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en">
<head>
 <link rel="shortcut icon" href="%s"/>
 <link rel="stylesheet" type="text/css" href="%s"/>
 <link rel="alternate" type="application/atom+xml" title="%s" href="%s"/>
 <title>%s</title>
</head>
""" % (get_res_path(request, rcfg.get_attribute("repository", "icon")),
    get_res_path(request, rcfg.get_attribute("repository", "style")),
    rcfg.get_attribute("feed", "name"), get_rel_path(request, "feed"),
    rcfg.get_attribute("repository", "name"))

        output += ("""\
<body>
 <div id="doc4" class="yui-t5">
  <div id="hd">
   <h1><img src="%s" alt="logo"/> <code>pkg</code> server ok</h1>
  </div>
  <div id="bd">
   <div id="yui-main" class="yui-b">
    <h2>Statistics</h2>
    <pre>
""") % (get_res_path(request, rcfg.get_attribute("repository", "logo")))
        output += scfg.get_status()
        output += """\
    </pre>
    <h2>Catalog</h2>
    <div>
     <table>
      <tr>
       <th>FMRI</th>
"""
        for op in fmri_ops:
                # Output a header for each possible operation for an FMRI.
                output += """\
       <th>%s</th>
""" % fmri_ops[op]
        output += """\
      </tr>
"""

        # Output each FMRI that we have in the catalog.
        flist = [f.get_fmri() for f in scfg.catalog.fmris()]
        flist.sort()
        for idx, pfmri in enumerate(flist):
                tr_class = idx % 2 and "even" or "odd"
                # Start FMRI entry
                output += """\
       <tr class="%s">
        <td>%s</td>
""" % (tr_class, pfmri)

                # Output all available operations for an FMRI.
                for op in fmri_ops:
                        output += """\
        <td><a href="%s">%s</a></td>
""" % (get_rel_path(request, "%s/0/%s" % (op, pfmri.lstrip('pkg:/'))),
    fmri_ops[op])

                # End FMRI entry
                output += """\
       </tr>
"""

        output += ("""\
     </table>
    </div>
    <div class="yui-b">
     <a href="%s"><img src="%s" alt="Atom feed" /></a>
     <p>Last Updated: %s</p>
    </div>
   </div>
  </div>
 </div>
</body>
</html>""") % (get_rel_path(request, "feed"),
    get_res_path(request, "feed-icon-32x32.png"),
    scfg.updatelog.last_update)

        return output

def feed(scfg, rcfg, request, response, *tokens, **params):
        if not scfg.updatelog.last_update:
                raise cherrypy.HTTPError(httplib.SERVICE_UNAVAILABLE,
                    "No update history; unable to generate feed.")

        return pkg.server.feed.handle(scfg, rcfg, cherrypy.request,
            cherrypy.response)

pages = {
        "" : index,
        "/feed" : feed,
        "/index.htm" :  index,
        "/index.html" :  index
}

def set_content_root(path):
        global content_root
        content_root = path

def match(scfg, rcfg, request, response):
        path = request.path_info.rstrip("/")
        if path in pages:
                return True
        return False

def respond(scfg, rcfg, request, response, *tokens, **params):
        path = request.path_info.rstrip("/")
        if path in pages:
                page = pages[path]
                return page(scfg, rcfg, request, response, *tokens, **params)
        else:
                return error(rcfg, request, response)

