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

# XXX Use small templating module?

# Non-HTML GET functions

def css(img, request):
        request.send_response(200)
        request.send_header('Content-type', 'text/css')
        request.end_headers()

        css = open("/usr/share/lib/pkg/pkg.css")

        request.wfile.write(css.read())

        css.close()

def icon(img, request):
        request.send_response(200)
        request.send_header('Content-type', 'image/png')
        request.end_headers()

        icon = open("/usr/share/lib/pkg/pkg-block-icon.png")

        request.wfile.write(icon.read())

        icon.close()

def logo(img, request):
        request.send_response(200)
        request.send_header('Content-type', 'image/png')
        request.end_headers()

        logo = open("/usr/share/lib/pkg/pkg-block-logo.png")

        request.wfile.write(logo.read())

        logo.close()

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
        request.send_response(404)
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
        request.wfile.write('''404 GET URI %s ; headers %s''' %
            (request.path, request.headers))
        request.wfile.write("""\
     </pre>
    </div>
   </div>
  </div>
 </div>
</body>
</html>
""" % request.path)

def error(img, request):
        request.send_response(500)
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
        request.wfile.write("%s" % img.catalog)
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
        "/index.html" : index,
        "/icon" :     icon,
        "/logo" :     logo,
        "/css" :      css
}

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
