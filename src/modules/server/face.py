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

"""face - dynamic index page for image packaging server"""

import os

from errno import ENOENT
from httplib import OK, NOT_FOUND, INTERNAL_SERVER_ERROR

# XXX Use small templating module?

# Non-HTML GET functions

content_root = "/usr/share/lib/pkg"

#
# Return the contents of a static file.
# Note that if filename is an absolute path, this will be used.
# Otherwise, the content root (PKG_DEPOT_CONTENT) directory will
# be prepended to the filename.
# If the static file cannot be found, an HTTP 404 (not found) error
# is returned. Any other errors in the open return an HTTP 500
# (internal server error).
#
# XXX Should we cache these files in memory as they are only small?
#
def send_static(img, request, filename, content_type):
        '''Open a given file and write the contents to the
           HTTP response stream'''
        rfile = None
        try:
                try:
                        _filename = os.path.join(content_root, filename)
                        rfile = open(_filename, 'rb')
                        data = rfile.read()
                        rfile.close()
                except IOError, ioe:
                        if ioe.errno == ENOENT:
                                # Not found: return a 404 error
                                unknown(img, request)
                        else:
                                # Otherwise push it up the stack
                                raise
                else:
                        request.send_response(OK)
                        request.send_header('Content-Type', content_type)
                        request.send_header('Content-Length', len(data))
                        request.end_headers()

                        request.wfile.write(data)
        except:
                if rfile:
                        rfile.close()
                error(img, request)
                raise


def css(img, request):
        send_static(img, request, "pkg.css", 'text/css')

def icon(img, request):
        send_static(img, request, "pkg-block-icon.png", 'image/png')

def logo(img, request):
        send_static(img, request, "pkg-block-logo.png", 'image/png')

def robots(img, request):
        send_static(img, request, "robots.txt", 'text/plain')

# HTML GET functions

def head(request, title = "pkg - image packaging system"):
        request.wfile.write("""\
<html>
<head>
 <link rel="shortcut icon" type="image/png" href="/icon">
 <link rel="stylesheet" type="text/css" href="/css">
 <title>%s</title>
</head>
""" % title)

def unknown(img, request):
        request.send_response(NOT_FOUND)
        request.send_header('Content-type', 'text/html')
        request.end_headers()
        head(request)
        request.wfile.write("""\
<body>
 <div id="doc4" class="yui-t5">
  <div id="hd">
   <h1><img src="/logo" /> <code>pkg</code> server unknown page</h1>
  </div>
  <div id="bd">
   <div id="yui-main">
    <div class="yui-b">
     <pre>
""")
        request.wfile.write('''404 GET URI %s ; headers:\n%s''' %
            (request.path, request.headers))
        request.wfile.write("""\
     </pre>
    </div>
   </div>
  </div>
 </div>
</body>
</html>
""")

def error(img, request):
        request.send_response(INTERNAL_SERVER_ERROR)
        request.send_header('Content-type', 'text/html')
        request.end_headers()
        head(request)
        request.wfile.write("""\
<body>
 <div id="doc4" class="yui-t5">
  <div id="hd">
   <h1><img src="/logo" /> <code>pkg</code> server internal error</h1>
  </div>
  <div id="bd">
   <div id="yui-main">
    <div class="yui-b">
     <pre>
face.response() for %s
     </pre>
    </div>
   </div>
  </div>
 </div>
</body>
</html>
""" % request.path)

def index(img, request):
        request.send_response(200)
        request.send_header('Content-type', 'text/html')
        request.end_headers()
        head(request)
        request.wfile.write("""\
<body>
 <div id="doc4" class="yui-t5">
  <div id="hd">
   <h1><img src="/logo" /> <code>pkg</code> server ok</h1>
  </div>
  <div id="bd">
   <div id="yui-main">
    <div class="yui-b">
     <h2>Statistics</h2>
     <pre>
""")
        request.wfile.write(img.get_status())
        request.wfile.write("""\
     </pre>

     <h2>Catalog</h2>
     <pre>
""")
        for f in img.catalog.fmris():
                request.wfile.write("%s\n" % f.get_fmri())
        request.wfile.write("""\
     </pre>
    </div>
   </div>
  </div>
 </div>
</body>
</html>""")

pages = {
        "/" : index,
        "/index.html" :  index,
        "/icon" :        icon,
        "/favicon.ico" : icon,
        "/logo" :        logo,
        "/css" :         css,
        "/robots.txt" :  robots
}

def set_content_root(path):
        global content_root
        content_root = path

def match(request):
        if request.path in pages.keys():
                return True
        return False

def respond(img, request):
        if request.path in pages.keys():
                page = pages[request.path]
                page(img, request)
        else:
                error(img, request)
